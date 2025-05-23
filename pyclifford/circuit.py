import numpy
import warnings
from .utils import mask, condense, pauli_diagonalize1
from .paulialg import Pauli, pauli, paulis, PauliMonomial, pauli_zero
from .stabilizer import (StabilizerState, CliffordMap, identity_map,
                         clifford_rotation_map, random_clifford_map)

class CliffordGate(object):
    '''Represents a Clifford unitary gate.

    Parameters:
    *qubits: int - the qubits that this gate acts on.

    Data:
    generator: Pauli - if the clifford gate is a rotation generated by a single 
        Pauli generator (which is generally not the case), then this records 
        its generator. It is more efficient to implement Clifford rotation than 
        generic Clifford transform.
    forward_map / backward_map: CliffordMap - a generic Clifford gate will be 
        described by the Clifford map, which is a table specifying how each 
        single Pauli operator gets mapped to. (forward and backward maps must 
        be inverse to each other).
    unitary: bool - indicates that gate is unitary.

    Note: if either the geneator or Clifford maps are specified, the gate will 
        represent the specific unitary transformation; otherwise, the gate 
        is treated as a random Clifford gate that resamples at every call.'''
    def __init__(self, *qubits):
        self.qubits = qubits # the qubits this gate acts on
        self.n = len(self.qubits) # number of qubits it acts on
        self.reset()
        self.unitary = True # gate is unitary

    def reset(self):
        # reset the gate to a random Clifford gate
        self.generator = None
        self.forward_map = None
        self.backward_map = None
    
    def __repr__(self):
        return '[{}]'.format(','.join(str(qubit) for qubit in self.qubits))
    
    def set_generator(self, gen):
        if not isinstance(gen, Pauli):
            raise TypeError("Rotation generator must be a Pauli string")
        self.generator = gen

    def set_forward_map(self,forward_map):
        if not isinstance(forward_map, CliffordMap):
            raise TypeError("Forward map must be a instance of CliffordMap")
        self.forward_map = forward_map

    def set_backward_map(self,backward_map):
        if not isinstance(backward_map, CliffordMap):
            raise TypeError("Backward map must be a instance of CliffordMap")
        self.backward_map = backward_map

    def copy(self):
        new = CliffordGate(*self.qubits)
        if self.generator is not None:
            new.generator = self.generator.copy()
        if self.forward_map is not None:
            new.forward_map = self.forward_map.copy()
        if self.backward_map is not None:
            new.backward_map = self.backward_map.copy()
        return new
    
    def independent_from(self, other):
        return len(set(self.qubits) & set(other.qubits))==0

    def forward(self, obj):
        '''Apply the gate forward in time. (inplace update)
        Forward transformation: O -> U O U^H

        Input:
        obj: Pauli, PauliList, StabilizerState - the object to be transformed
             
        Output:
        obj: (same as input type) - the object after the gate is applied
        log2prob: real - always 0.0 for unitary transformation'''
        if self.generator is not None: # if generator is given, use generator
            if self.n == obj.N: # global gate
                obj.rotate_by(self.generator)
            else: # local gate
                obj.rotate_by(self.generator, mask(self.qubits, obj.N))
        else: # if generator not given, check maps
            if self.forward_map is None:
                if self.backward_map is None: 
                    # if both maps not given, treated as random gate
                    clifford_map = random_clifford_map(self.n)
                    self.forward_map = clifford_map # record as forward map
                else:
                    self.forward_map = self.backward_map.inverse()
                    clifford_map = self.forward_map
            else:
                clifford_map = self.forward_map
            if self.n == obj.N: # global gate
                obj.transform_by(clifford_map)
            else: # local gate
                obj.transform_by(clifford_map, mask(self.qubits, obj.N))
        log2prob = 0.0 # unitary gate is deterministic, log2prob is always 0.0
        return obj, log2prob

    def backward(self, obj):
        '''Apply the gate backward in time. (inplace update)
        Backward transformation: O -> U^H O U

        Input:
        obj: Pauli, PauliList, StabilizerState - the object to be transformed
             
        Output:
        obj: (same as input type) - the object after the gate is applied
        log2prob: real - always 0.0 for unitary transformation'''
        if self.generator is not None: # if generator is given, use generator
            if self.n == obj.N: # global gate
                obj.rotate_by(-self.generator)
            else: # local gate
                obj.rotate_by(-self.generator, mask(self.qubits, obj.N))
        else: # if generator not given, check maps
            if self.backward_map is None:
                if self.forward_map is None: 
                    # if both maps not given, treated as random gate
                    clifford_map = random_clifford_map(self.n)
                    self.backward_map = clifford_map # record as backward map
                else:
                    self.backward_map = self.forward_map.inverse()
                    clifford_map = self.backward_map
            else:
                clifford_map = self.backward_map
            if self.n == obj.N: # global gate
                obj.transform_by(clifford_map)
            else: # local gate
                obj.transform_by(clifford_map, mask(self.qubits, obj.N))
        log2prob = 0.0 # unitary gate is deterministic, log2prob is always 0.0
        return obj, log2prob

    def compile(self):
        '''Construct forward and backward Clifford maps for this gate'''
        if self.generator is not None:
            self.forward_map = clifford_rotation_map(self.generator)
            self.backward_map = clifford_rotation_map(-self.generator)
        else:
            if self.forward_map is None:
                if self.backward_map is None:
                    raise Exception('random Clifford gate can not be compiled.')
                else:
                    self.forward_map = self.backward_map.inverse()
            else:
                if self.backward_map is None:
                    self.backward_map = self.forward_map.inverse()
        return self

class Measurement(object):
    '''Represents a computational basis measurement.
    
    Parameters:
    *qubits: int - the qubits to be measured
    
    Data:
    out: int (L) - array of measurement outcomes on corresponding qubits
         None before measurement, populated after forward measurement.
    unitary: bool - indicates that measurement is not unitary.'''
    def __init__(self, *qubits):
        self.qubits = qubits # the qubits to be measured
        self.n = len(self.qubits) # number of qubits to be measured
        self._out = None  # container for measurement outcomes, will be populated after forward measurement
        self.unitary = False # measurement is not unitary

    def reset(self):
        self._out = None

    @property
    def out(self):
        if self._out is None:
            raise ValueError("{} measurement outcome is not sampled yet.".format(repr(self)))
        return self._out

    @out.setter
    def out(self, out):
        self._out = out

    def __repr__(self):
        return '<{}>'.format(','.join(str(qubit) for qubit in self.qubits))

    
    def copy(self):
        new = Measurement(*self.qubits)
        if self._out is not None:
            new._out = self._out.copy()
        return new
    
    def independent_from(self, other):
        return len(set(self.qubits) & set(other.qubits))==0

    def forward(self, obj):
        '''Implements the measurement (non-deterministic sampling outcome).
        (inplace update)
        Forward transformation: rho -> M rho M^H / Tr(M rho M^H),
        where M is sampled with probability Tr(M rho M^H).
        
        Input:
        obj: StabilizerState - the state to be measured
        
        Output:
        obj: StabilizerState - the state after measurement
        log2prob: real - log2 probability of the outcome'''
        if not isinstance(obj, StabilizerState): # measurement only applicable to stabilizer state
            raise NotImplementedError("the object {} is not a stabilizer state".format(repr(obj)))
        # construct Z observables
        obs = paulis(pauli({i: 'Z'}, obj.N) for i in self.qubits)
        # perform measurement
        self.out, log2prob = obj.measure(obs)
        return obj, log2prob

    def backward(self, obj):
        '''Postselect the measurement outcome (deterministic projection).
        (inplace update)
        Backward transformation: rho -> M^H rho M / Tr(M^H rho M)
        where M is fixed by the measurement outcome generated in the forward pass.
        
        Input:
        obj: StabilizerState - the state to be postselected     
        
        Output:
        obj: StabilizerState - the state after postselection
        log2prob: real - log2 probability of successful postselection'''
        if not isinstance(obj, StabilizerState): # postselection only applicable to stabilizer state
            raise NotImplementedError("the object {} is not a stabilizer state".format(repr(obj)))
        # construct Z observables
        obs = paulis(pauli({i: 'Z'}, obj.N) for i in self.qubits)
        log2prob = obj.postselect(obs, self.out)
        if log2prob == -numpy.inf: # if postselection fails
            warnings.warn("Impossible to postselect the recorded measurement outcomes on the current state in the backward pass. The resutlting state might be incorrect.")
        return obj, log2prob


class Layer(object):
    '''Representes a layer of Clifford gate or measurement operations.

    Parameters:
    *ops: Operation - the operations (gates or measurements) in this layer

    Attributes:
    prev_layer: Layer - the previous layer
    next_layer: Layer - the next layer
    forward_map: CliffordMap - the forward map of the layer (if unitary)
    backward_map: CliffordMap - the backward map of the layer (if unitary)
    unitary: bool - whether the layer is unitary'''

    def __init__(self, *ops):
        self.ops = list(ops)    # the operations in this layer
        self.prev_layer = None  # the previous layer
        self.next_layer = None  # the next layer
        self.forward_map = None
        self.backward_map = None
        # the layer is unitary if all operations are unitary
        self.unitary = all(op.unitary for op in self.ops)

    def reset(self):
        self.forward_map = None
        self.backward_map = None
        for op in self.ops:
            op.reset()

    @property
    def out(self):
        outs = [op.out for op in self.ops if not op.unitary]
        if outs:
            return numpy.concatenate(outs)
        else:
            return numpy.array([], dtype=numpy.int_)

    @out.setter
    def out(self, out):
        if not self.unitary:
            k = 0
            for op in self.ops:
                if not op.unitary:
                    op.out = out[k:k+op.n]
                    k += op.n

    def __repr__(self):
        return '|{}|'.format(''.join(repr(op) for op in self.ops))
    
    @property
    def isempty(self):
        return len(self.ops) == 0
    
    def copy(self):
        new = Layer(*(op.copy() for op in self.ops))
        if self.forward_map is not None:
            new.forward_map = self.forward_map.copy()
        if self.backward_map is not None:
            new.backward_map = self.backward_map.copy()
        return new
    
    def independent_from(self, other):
        return all(op.independent_from(other) for op in self.ops)
    
    def append(self, op):
        '''append an operation into this layer.'''
        if (self.prev_layer is not None) and self.prev_layer.independent_from(op):
            # if the previous layer exists and is independent from the new operation
            self.prev_layer.append(op) # append the operation to the previous layer
        else: # otherwise, admit the new operation to the current layer
            self.ops.append(op) 
            self.unitary = self.unitary and op.unitary
        # Clear cached maps since layer had changed
        self.forward_map = None
        self.backward_map = None
        return self
    
    def forward(self, obj):
        '''Apply the layer forward. (inplace update)'''
        log2prob = 0.0
        if self.unitary and self.forward_map is not None:
            obj.transform_by(self.forward_map) 
        else: # otherwise, apply each operation forward (in parallel)
            for op in self.ops:
                obj, op_log2prob = op.forward(obj)
                log2prob += op_log2prob
        return obj, log2prob
    
    def backward(self, obj):
        '''Apply the layer backward. (inplace update)'''
        log2prob = 0.0
        if self.unitary and self.backward_map is not None:
            # if layer backward map has been compiled, use it
            obj.transform_by(self.backward_map)
        else: # otherwise, apply each operation backward (in parallel)
            for op in self.ops:
                obj, op_log2prob = op.backward(obj)
                log2prob += op_log2prob
        return obj, log2prob
    
    def compile(self, N):
        '''construct forward and backward Clifford maps for this layer
        
        Input:
        N: int - number of qubits in the system'''
        if not self.unitary:
            raise ValueError("only unitary layer can be compiled.")
        self.forward_map = identity_map(N)
        self.backward_map = identity_map(N)
        for op in self.ops:
            op.compile()
            self.forward_map.embed(op.forward_map, mask(op.qubits, N))
            self.backward_map.embed(op.backward_map, mask(op.qubits, N))
        return self 
    

class Circuit(object):
    '''Represents a quantum process of Clifford circuit with gates and measurements.

    Attributes:
    first_layer: Layer - the first layer of the circuit
    last_layer: Layer - the last layer of the circuit
    forward_map: CliffordMap - the forward map of the circuit (if unitary)
    backward_map: CliffordMap - the backward map of the circuit (if unitary)
    unitary: bool - whether the circuit is unitary
    
    Example:
    >>> circ = Circuit()
    >>> circ.gate(0)
    >>> circ.measure(1)
    >>> circ.gate(2)
    >>> sigma, log2prob_fw = circ.forward(zero_state(N))
    >>> rho, log2prob_bw = circ.backward(sigma.copy())
    >>> print(sigma, rho, log2prob_fw, log2prob_bw)
    '''
    def __init__(self, *objs):
        self.first_layer = Layer()
        self.last_layer = self.first_layer
        self.forward_map = None # forward map
        self.backward_map = None # backward map
        self.unitary = True # empty circuit is unitary
        # append objects to the circuit
        # each object can be CliffordGate, Measurement, Layer, or Circuit
        for obj in objs:
            self.append(obj)

    def reset(self):
        self.forward_map = None
        self.backward_map = None
        for layer in self.layers_forward():
            layer.reset()

    @property
    def out(self):
        outs = [layer.out for layer in self.layers_forward() if not layer.unitary]
        if outs:
            return numpy.concatenate(outs)
        else:
            return numpy.array([], dtype=numpy.int_)

    @out.setter
    def out(self, out):
        print('out:', out) # for debug
        k = 0
        for layer in self.layers_forward():
            print(layer, layer.unitary) # for debug
            if not layer.unitary:
                n = sum(op.n for op in layer.ops if not op.unitary)
                print('number measurement:', n) # for debug
                print('out[k:k+n]:', out[k:k+n]) # for debug
                layer.out = out[k:k+n]
                k += n

    def __repr__(self):
        layout = '\n'.join(repr(layer) for layer in self.layers_backward())
        c =  'Circuit(\n{})'.format(layout).replace('\n','\n  ')
        return c

    def layers_backward(self):
        # yield from last to first layers
        layer = self.last_layer
        while layer is not None:
            yield layer
            layer = layer.prev_layer

    def layers_forward(self):
        # yield from first to last layers
        layer = self.first_layer
        while layer is not None:
            yield layer
            layer = layer.next_layer

    def append_layer(self, layer):
        # add a layer to the circuit (helper method not to be used directly)
        # will not update unitary property and cached maps
        if layer.isempty: # ignore empty layer
            return self
        if self.last_layer.isempty:
            # use the layer as the last layer
            if self.last_layer is self.first_layer:
                self.first_layer = layer
            layer.prev_layer = self.last_layer.prev_layer
            layer.next_layer = self.last_layer.next_layer
        else: # otherwise, attach the layer to the last layer
            self.last_layer.next_layer = layer
            layer.prev_layer = self.last_layer
        self.last_layer = layer
        return self

    def append(self, op):
        ''' Add an operation (gate or measurement) to the circuit.
            This method tries to append the operation to the last layer if independent.
            If not, a new Layer is created.'''
        if isinstance(op, CliffordGate) or isinstance(op, Measurement):
            # add an operation to the circuit
            if self.last_layer.independent_from(op):
                self.last_layer.append(op)
            else:
                self.append_layer(Layer(op))
        elif isinstance(op, Layer):
            # attach a layer to the circuit
            self.append_layer(op)
        elif isinstance(op, Circuit):
            # compose a circuit to the circuit
            for layer in op.layers_forward():
                self.append_layer(layer)
        else:
            raise ValueError("Unsupported operation type {} to be appended to circuit.".format(type(op)))
        # Update unitary property
        self.unitary = self.unitary and op.unitary
        # Clear cached maps since circuit had changed
        self.forward_map = None
        self.backward_map = None
        return self

    def gate(self, *qubits):
        '''Add a Clifford gate to the circuit'''
        return self.append(CliffordGate(*qubits))

    def measure(self, *qubits):
        '''Add a measurement to the circuit'''
        return self.append(Measurement(*qubits))

    def forward(self, obj):
        '''Apply the circuit forward to a quantum object. (inplace update)'''
        log2prob = 0.0
        if self.forward_map is not None and self.unitary:
            # if circuit forward map has been compiled, use it
            obj.transform_by(self.forward_map)
        else: # otherwise, apply each layer forward (in forward sequence)
            for layer in self.layers_forward():
                obj, layer_log2prob = layer.forward(obj)
                log2prob += layer_log2prob
        return obj, log2prob

    def backward(self, obj):
        '''Apply the circuit backward to a quantum object. (inplace update)'''
        log2prob = 0.0
        if self.backward_map is not None and self.unitary:
            # if circuit backward map has been compiled, use it
            obj.transform_by(self.backward_map)
        else: # otherwise, apply each layer backward (in backward sequence)
            for layer in self.layers_backward():
                obj, layer_log2prob = layer.backward(obj)
                log2prob += layer_log2prob
        return obj, log2prob

    def compile(self, N):
        '''Compile the circuit into forward/backward maps where possible (unitary only).
        
        Input:
        N: int - number of qubits in the system'''
        if self.unitary:
            for layer in self.layers_forward():
                layer.compile(N)
            self.forward_map = identity_map(N)
            self.backward_map = identity_map(N)
            for layer in self.layers_forward():
                self.forward_map = self.forward_map.compose(layer.forward_map)
                self.backward_map = layer.backward_map.compose(self.backward_map)
        return self

# ---- gate constructors ----
def clifford_rotation_gate(generator, qubits=None):
    '''Construct a Clifford rotation gate generted by a generator.

    Parameters:
    generator: Pauli - Pauli operator that generates the rotation.
        U = exp( i pi/4 g) = (1 + i g)/sqrt(2)'''
    generator = pauli(generator)
    g_cond, qubits_cond = condense(generator.g) # extract generator support
    if qubits is None:
        qubits = qubits_cond
    else:
        qubits = qubits[qubits_cond]
    gate = CliffordGate(*qubits)
    gate.generator = Pauli(g_cond, generator.p) # condensed generator
    return gate

# ---- circuit constructors ----
def identity_circuit(N = None):
    '''Construct a identity Clifford circuit containing no gate.

    Parameters:
    N: int - number of qubits.'''
    circ = Circuit()
    if N is not None:
        circ.N = N  # fix number of qubits explicitly
    return circ

def brickwall_rcc(N, depth):
    '''Construct random Clifford circuit with brick wall circuit structure.

    Parameters:
    N: int - number of qubits.
    depth: int - circuit depth.'''
    assert(N % 2 == 0) # N should be even
    circ = identity_circuit(N)
    for l in range(depth):
        for i in range(l % 2, N, 2):
            circ.gate(i, (i+1) % N)
    return circ

def onsite_rcc(N):
    '''Construct random Clifford circuit of a layer of single-site gates.
       (useful for implementing random Pauli measurements)

    Parameters:
    N: int - number of qubits.'''
    circ = identity_circuit(N)
    for i in range(N):
        circ.gate(i)
    return circ

def global_rcc(N):
    '''Construct random Clifford circuit of a global Clifford gate.
       (useful for implementing random Clifford measurements)

    Parameters:
    N: int - number of qubits.'''
    circ = identity_circuit(N)
    circ.gate(*range(N))
    return circ

def measurement_layer(N):
    '''Construct a layer of computational basis measurements.
       (to be combined with unitary circuit to form a measurement circuit)
    
    Parameters:
    N: int - number of qubits.'''
    circ = identity_circuit(N)
    circ.measure(*range(N))
    return circ

# ---- single qubit gates ----
def H(*qubits):
    if len(qubits)!=1:
        raise ValueError("Hadmand gate only acts on a single qubit.")
    gate = CliffordGate(*qubits)
    f_map = CliffordMap(gs = numpy.array([[0,1],[1,0]]),ps = numpy.array([0,0]))
    gate.set_forward_map(f_map)
    return gate

def S(*qubits):
    if len(qubits)!=1:
        raise ValueError("S gate only acts on a single qubit.")
    gate = CliffordGate(*qubits)
    f_map = CliffordMap(gs = numpy.array([[1,1],[0,1]]),ps = numpy.array([0,0]))
    gate.set_forward_map(f_map)
    return gate

def X(*qubits):
    if len(qubits)!=1:
        raise ValueError("X gate only acts on a single qubit.")
    gate = CliffordGate(*qubits)
    f_map = CliffordMap(gs = numpy.array([[1,0],[0,1]]),ps = numpy.array([0,2]))
    gate.set_forward_map(f_map)
    return gate

def Y(*qubits):
    if len(qubits)!=1:
        raise ValueError("Y gate only acts on a single qubit.")
    gate = CliffordGate(*qubits)
    f_map = CliffordMap(gs = numpy.array([[1,0],[0,1]]),ps = numpy.array([2,2]))
    gate.set_forward_map(f_map)
    return gate

def Z(*qubits):
    if len(qubits)!=1:
        raise ValueError("Z gate only acts on a single qubit.")
    gate = CliffordGate(*qubits)
    f_map = CliffordMap(gs = numpy.array([[1,0],[0,1]]),ps = numpy.array([2,0]))
    gate.set_forward_map(f_map)
    return gate

def C(num, *qubits):
    # single qubit Clifford gate, num: 0-23
    if len(qubits)!=1:
        raise ValueError("Single qubit Clifford gate acts on single qubit.")
    gate = CliffordGate(*qubits)
    if num == 0:
        f_map = CliffordMap(gs = numpy.array([[1,0],[1,1]]),ps = numpy.array([0,0]))
    elif num == 1:
        f_map = CliffordMap(gs = numpy.array([[1,0],[1,1]]),ps = numpy.array([0,2]))
    elif num == 2:
        f_map = CliffordMap(gs = numpy.array([[1,0],[0,1]]),ps = numpy.array([0,0]))
    elif num == 3:
        f_map = CliffordMap(gs = numpy.array([[1,0],[0,1]]),ps = numpy.array([0,2]))
    elif num == 4:
        f_map = CliffordMap(gs = numpy.array([[1,0],[1,1]]),ps = numpy.array([2,0]))
    elif num == 5:
        f_map = CliffordMap(gs = numpy.array([[1,0],[1,1]]),ps = numpy.array([2,2]))
    elif num == 6:
        f_map = CliffordMap(gs = numpy.array([[1,0],[0,1]]),ps = numpy.array([0,2]))
    elif num == 7:
        f_map = CliffordMap(gs = numpy.array([[1,0],[0,1]]),ps = numpy.array([2,2]))
    elif num == 8:
        f_map = CliffordMap(gs = numpy.array([[1,1],[1,0]]),ps = numpy.array([0,0]))
    elif num == 9:
        f_map = CliffordMap(gs = numpy.array([[1,1],[1,0]]),ps = numpy.array([0,2]))
    elif num == 10:
        f_map = CliffordMap(gs = numpy.array([[1,1],[0,1]]),ps = numpy.array([0,0]))
    elif num == 11:
        f_map = CliffordMap(gs = numpy.array([[1,1],[0,1]]),ps = numpy.array([0,2]))
    elif num == 12:
        f_map = CliffordMap(gs = numpy.array([[1,1],[1,0]]),ps = numpy.array([2,0]))
    elif num == 13:
        f_map = CliffordMap(gs = numpy.array([[1,1],[1,0]]),ps = numpy.array([2,2]))
    elif num == 14:
        f_map = CliffordMap(gs = numpy.array([[1,1],[0,1]]),ps = numpy.array([2,0]))
    elif num == 15:
        f_map = CliffordMap(gs = numpy.array([[1,1],[0,1]]),ps = numpy.array([2,2]))
    elif num == 16:
        f_map = CliffordMap(gs = numpy.array([[0,1],[1,0]]),ps = numpy.array([0,0]))
    elif num == 17:
        f_map = CliffordMap(gs = numpy.array([[0,1],[1,0]]),ps = numpy.array([0,2]))
    elif num == 18:
        f_map = CliffordMap(gs = numpy.array([[0,1],[1,1]]),ps = numpy.array([0,0]))
    elif num == 19:
        f_map = CliffordMap(gs = numpy.array([[0,1],[1,1]]),ps = numpy.array([0,2]))
    elif num == 20:
        f_map = CliffordMap(gs = numpy.array([[0,1],[1,0]]),ps = numpy.array([2,0]))
    elif num == 21:
        f_map = CliffordMap(gs = numpy.array([[0,1],[1,0]]),ps = numpy.array([2,2]))
    elif num == 22:
        f_map = CliffordMap(gs = numpy.array([[0,1],[1,1]]),ps = numpy.array([2,0]))
    elif num == 23:
        f_map = CliffordMap(gs = numpy.array([[0,1],[1,1]]),ps = numpy.array([2,2]))
    else:
        raise ValueError("There are only 24 single qubit Clifford gate. Input number exceed 0-23.")
    gate.set_forward_map(f_map)
    return gate

# ---- two qubit gates ----
def CNOT(*qubits):
    if len(qubits)!=2:
        raise ValueError("CNOT gate acts on two qubit.")
    gate = CliffordGate(*qubits)
    if qubits[0]<qubits[1]:
        f_map = CliffordMap(gs = numpy.array([[1,0,1,0],[0,1,0,0],[0,0,1,0],[0,1,0,1]]),ps = numpy.array([0,0,0,0]))
    else:
        f_map = CliffordMap(gs = numpy.array([[1,0,0,0],[0,1,0,1],[1,0,1,0],[0,0,0,1]]),ps = numpy.array([0,0,0,0]))
    gate.set_forward_map(f_map)
    return gate

def SWAP(*qubits):
    if len(qubits)!=2:
        raise ValueError("SWAP gate acts on two qubit.")
    gate = CliffordGate(*qubits)
    gate.set_forward_map(CliffordMap(gs = numpy.array([[0,0,1,0],[0,0,0,1],[1,0,0,0],[0,1,0,0]]),ps = numpy.array([0,0,0,0])))
    return gate
        
def CZ(*qubits):
    if len(qubits)!=2:
        raise ValueError("CZ gate acts on two qubit.")
    gate = CliffordGate(*qubits)
    gate.set_forward_map(CliffordMap(gs = numpy.array([[1,0,0,1],[0,1,0,0],[0,1,1,0],[0,0,0,1]]),ps = numpy.array([0,0,0,0])))
    return gate

def CX(*qubits):
    return CNOT(*qubits)

# ---- diagonalization ----
def diagonalize(obj, i0 = 0, causal=False):
    '''Diagonalize a Pauli operator or a stabilizer state (density matrix).

    Parameters:
    obj: Pauli, PauliMonomial - the operator to be diagonalized, or
         StabilizerState - the state to be diagonalized.
    i0: int - index of the qubit to diagonalize to.
    causal: bool - whether to preserve the causal structure by restricting 
                   the action of Clifford transformation to the qubits at i0 and afterwards.

    Returns:
    circ: Circuit - circuit that diagonalizes obj.'''
    circ = identity_circuit(obj.N)
    if isinstance(obj, (Pauli, PauliMonomial)):
        if causal:
            for g in pauli_diagonalize1(obj.g[2*i0:]):
                circ.append(clifford_rotation_gate(Pauli(g), numpy.arange(i0,obj.N)))
        else:
            for g in pauli_diagonalize1(obj.g, i0):
                circ.append(clifford_rotation_gate(Pauli(g)))
    elif isinstance(obj, StabilizerState):
        gate = CliffordGate(*numpy.arange(obj.N))
        gate.backward_map = obj.to_map() # set backward map to encoding map
        # then the forward map automatically decodes (= diagonalize) the state
        circ.append(gate)
    else:
        raise NotImplementedError('diagonalization is not implemented for {}.'.format(type(obj).__name__))
    return circ


def SBRG(hmdl, max_rate=2., tol=1.e-8):
    '''Approximately diagonalize a Hamiltonian by SBRG.

    Parameters:
    hmdl: PauliPolynomial - model Hamiltonian.

    Returns:
    heff: PauliPolynomial - effective Hamiltonian in spectrum bifurcation basis.
    circ: Circuit - Clifford circuit to approximately diagonalize the Hamiltonian.'''
    htmp = hmdl.copy() # copy of model Hamiltonian to workspace
    N = htmp.N # system size
    circ = identity_circuit(N) # create circuit
    heff = pauli_zero(N) # create effective Hamiltonian
    # SBRG iteration
    for i0 in range(N): # pivot through every qubit
        if len(htmp) == 0:
            break
        leading = numpy.argmax(numpy.abs(htmp.cs)) # get leading term index
        # find circuit to diagonalize leading term to i0
        circ_i0 = diagonalize(htmp[leading], i0, causal=True)
        circ.compose(circ_i0) # append it to total circuit
        circ_i0.forward(htmp) # apply it to Hamiltonian
        mask_commute = htmp.gs[:,2*i0] == 0 # mask diagonal terms
        len_anti = sum(~mask_commute) # count number of offdiagonal terms
        if len_anti != 0: # if offdiagonal terms exist
            # split diagonal from offdiagonal terms
            diag = htmp[mask_commute]
            offdiag = htmp[~mask_commute]
            # eleminate offdiagonal terms by perturbation theory
            len_max = int(round(max_rate * len_anti)) # max perturbation terms to keep
            prod = (offdiag @ offdiag).reduce(tol)[:len_max]
            if len(prod) != 0:
                htmp = diag + 0.5 * (htmp[leading].inverse() @ prod)
        # mask terms that has become trivial on the remaining qubits
        mask_trivial = numpy.all(htmp.gs[:,(2*i0+2):] == 0, -1)
        heff += htmp[mask_trivial] # collect trivial terms to effective Hamiltonian
        htmp = htmp[~mask_trivial] # retain with non-trivial terms
    return heff, circ

