from bytecode import BasicBlock,Instr,UNSET,Compare,Label
from boa.interop import VMOp
from boa.code import pyop
import binascii
import opcode as _opcode
import pdb





class Expression(object):

    updated_blocklist = None
    block = None
    orig_block = None
    tokenizer = None


    methodnames = None

    def __init__(self,block:list, tokenizer):
        self.block = block
        self.orig_block = block
        self.tokenizer = tokenizer
        self.methodnames = []

    def add_method(self, pytoken):

        self.methodnames.append( pytoken.instruction.arg)

        print("CURRENT METHODS %s " % self.methodnames)

    def _reverselists(self):
        indices = []
        for index,instr in enumerate(self.updated_blocklist):
            if not isinstance(instr, Label) and instr.opcode == pyop.BUILD_LIST:
                indices.append(index)
        if len(indices):
            output = []
            for index, instr in enumerate(self.updated_blocklist):
                output.append(instr)
                if index in indices:
                    output.append(Instr("DUP_TOP",lineno=instr.lineno))
                    output.append(Instr('YIELD_VALUE',lineno=instr.lineno))
            self.updated_blocklist = output

    def _checkbytearray(self):
        to_remove=[]
        for index,instr in enumerate(self.block):
            if not isinstance(instr, Label) and instr.opcode == pyop.LOAD_GLOBAL and instr.arg == 'bytearray':
                to_remove.append(instr)
                to_remove.append(self.block[index+2])
        if len(to_remove):
            self._remove_instructions(to_remove)

    def _check_load_attr(self):
        replaceable_attr_calls = ['append','remove','reverse',]
        for index,instr in enumerate(self.block):
            if not isinstance(instr, Label) and instr.opcode == pyop.LOAD_ATTR and instr.arg in replaceable_attr_calls:
                instr.opcode = pyop.LOAD_GLOBAL

    def _check_function_kwargs(self):
        to_remove = []
        for index, instr in enumerate(self.updated_blocklist):
            if not isinstance(instr, Label) and instr.opcode == pyop.CALL_FUNCTION_KW:
                instr.opcode = pyop.CALL_FUNCTION
                to_remove.append(self.updated_blocklist[index-1])
        if len(to_remove):
            self._remove_instructions(to_remove)

    def _remove_instructions(self, to_remove):
        updated = []
        for item in self.block:
            if not item in to_remove:
                updated.append(item)
        self.updated_blocklist = updated




    def tokenize(self):


        self.updated_blocklist = self.block
        self._checkbytearray()
#        self._checkloops(method)
        self._check_function_kwargs()
        self._check_load_attr()
        self._reverselists()

        ln = None
        for index,instr in enumerate(self.updated_blocklist):
            if isinstance(instr, Instr):
                ln = instr.lineno
            token = PyToken(instr, self, index, ln)
            token.to_vm(self.tokenizer)


    def lookup_method_name(self, index):
        return self.methodnames.pop()

class PyToken():

    instruction = None # type:Instr
    expression = None # type:Expression
    index = 0

    jump_found = False

    jump_target = None
    jump_from = None
    jump_from_addr = None
    jump_to_addr = None

    _methodname = None

    def __init__(self, instruction, expression, index, fallback_ln):
        self.instruction = instruction
        self.expression = expression
        self.index = index
        self._methodname = None
        self.jump_from = None
        self.jump_target = None
        self.jump_found = False
        self.jump_from_addr = None
        self.jump_to_addr = None
        if isinstance(instruction, Label):
            self.jump_target = instruction
            self.instruction = Instr("NOP",lineno=fallback_ln)
        elif isinstance(instruction.arg, Label):
            self.jump_from = instruction.arg

    @property
    def lineno(self):
        return self.instruction.lineno

    @property
    def arg_str(self):
#        print("INSTRUCTION ARG: %s %s" % (type(self.instruction.arg), self.instruction.arg))
        params = ['a','b','c','d','e','f','g','h','i','j','k','l','m']
        if self.jump_target:
            return 'from %s ' % self.jump_from_addr
        elif self.jump_from:
            return 'to %s ' % self.jump_to_addr
        elif self._methodname:
            return '%s(%s)' % (self._methodname, ','.join(params[0:self.instruction.arg]))
        elif isinstance(self.instruction.arg, Compare):
            return self.instruction.arg.name
        elif isinstance(self.instruction.arg, bytes) or isinstance(self.instruction.arg, bytearray):
            return str(self.instruction.arg)
        return self.instruction.arg if self.instruction.arg != UNSET else ''

    @property
    def args(self):
        return self.instruction.arg

    @property
    def pyop(self):
        return self.instruction.opcode

    @property
    def func_name(self):
        if not self._methodname:
            self._methodname = self.expression.lookup_method_name(self.index)
        return self._methodname

    @property
    def num_params(self):
        return self.args

    def to_vm(self, tokenizer):
        """

        :param tokenizer:
        :param prev_token:
        :return:
        """

        from boa.compiler import Compiler

        op = self.instruction.opcode
#        print("CONVERTING OP: %s %s " % (self.instruction.name, self.instruction.arg))

        if op == pyop.NOP:
            tokenizer.convert1(VMOp.NOP, self)

        elif op == pyop.RETURN_VALUE:
            tokenizer.method_end_items()
            tokenizer.convert1(VMOp.RET, self)

        # control flow
        elif op == pyop.BR_S:
            tokenizer.convert1(VMOp.JMP, self, data=self.instruction.arg)

        elif op == pyop.JUMP_FORWARD:
            tokenizer.convert1(VMOp.JMP, self, data=bytearray(2))

        elif op == pyop.JUMP_ABSOLUTE:
            tokenizer.convert1(VMOp.JMP, self, data=bytearray(2))

        elif op == pyop.POP_JUMP_IF_FALSE:
            tokenizer.convert1(
                VMOp.JMPIFNOT, self, data=bytearray(2))

        elif op == pyop.POP_JUMP_IF_TRUE:
            tokenizer.convert_pop_jmp_if(self)
        # loops
        elif op == pyop.SETUP_LOOP:
            tokenizer.convert1(VMOp.NOP, self, data=bytearray(2))
        elif op == pyop.BREAK_LOOP:
            tokenizer.convert1(VMOp.JMP, self, data=bytearray(2))

        elif op == pyop.FOR_ITER:
            tokenizer.convert1(VMOp.NOP, self, data=bytearray(2))

        elif op == pyop.GET_ITER:
            tokenizer.convert1(VMOp.NOP, self)

        elif op == pyop.POP_BLOCK:
            tokenizer.convert1(VMOp.NOP, self)

        elif op == pyop.FROMALTSTACK:
            tokenizer.convert1(VMOp.FROMALTSTACK, self)
        elif op == pyop.DROP:
            tokenizer.convert1(VMOp.DROP, self)
        elif op == pyop.XSWAP:
            tokenizer.convert1(VMOp.XSWAP, self)
        elif op == pyop.ROLL:
            tokenizer.convert1(VMOp.ROLL, self)

        # loading constants ( ie 1, 2 etc)
        elif op == pyop.LOAD_CONST:
            tokenizer.convert_load_const(self)

        # storing / loading local variables
        elif op in [pyop.STORE_FAST, pyop.STORE_NAME]:
            tokenizer.convert_store_local(self)
        elif op == pyop.LOAD_GLOBAL:

            default_module = Compiler.instance().default
            self.expression.add_method(self)
#            tokenizer.convert1(VMOp.NOP, self)
#            if default_module.method_by_name(self.args):
#                print("FOUND METHOD BY NAME: %s " % self.args)
 #           else:
 #               print("COULD NOT LOCATE METHOD BY NAME %s " % self.args)

        elif op in [pyop.LOAD_FAST, pyop.LOAD_NAME]:
            tokenizer.convert_load_local(self)

        # unary ops

#            elif op == pyop.UNARY_INVERT:
#                tokenizer.convert1(VMOp.INVERT, self)

        elif op == pyop.UNARY_NEGATIVE:
            tokenizer.convert1(VMOp.NEGATE, self)

        elif op == pyop.UNARY_NOT:
            tokenizer.convert1(VMOp.NOT, self)

#            elif op == pyop.UNARY_POSITIVE:
            # hmmm
#                tokenizer.convert1(VMOp.ABS, self)
#                pass

        # math
        elif op in [pyop.BINARY_ADD, pyop.INPLACE_ADD]:

            # we can't tell by looking up the last token what type of item it was
            # will need to figure out a different way of concatting strings
            #                if prev_token and type(prev_token.args) is str:
            #                    tokenizer.convert1(VMOp.CAT, self)
            #                else:
            tokenizer.convert1(VMOp.ADD, self)

        elif op in [pyop.BINARY_SUBTRACT, pyop.INPLACE_SUBTRACT]:
            tokenizer.convert1(VMOp.SUB, self)

        elif op in [pyop.BINARY_MULTIPLY, pyop.INPLACE_MULTIPLY]:
            tokenizer.convert1(VMOp.MUL, self)

        elif op in [pyop.BINARY_FLOOR_DIVIDE, pyop.BINARY_TRUE_DIVIDE,
                    pyop.INPLACE_FLOOR_DIVIDE, pyop.INPLACE_TRUE_DIVIDE]:
            tokenizer.convert1(VMOp.DIV, self)

        elif op in [pyop.BINARY_MODULO, pyop.INPLACE_MODULO]:
            tokenizer.convert1(VMOp.MOD, self)

        elif op == [pyop.BINARY_OR, pyop.INPLACE_OR]:
            tokenizer.convert1(VMOp.BOOLOR, self)

        elif op == [pyop.BINARY_AND, pyop.INPLACE_AND]:
            tokenizer.convert1(VMOp.BOOLAND, self)

        elif op == [pyop.BINARY_XOR, pyop.INPLACE_XOR]:
            tokenizer.convert1(VMOp.XOR, self)

        elif op in [pyop.BINARY_LSHIFT, pyop.INPLACE_LSHIFT]:
            tokenizer.convert1(VMOp.SHL, self)

        elif op in [pyop.BINARY_RSHIFT, pyop.INPLACE_RSHIFT]:
            tokenizer.convert1(VMOp.SHR, self)

        # compare

        elif op == pyop.COMPARE_OP:

#            pdb.set_trace()
            if self.instruction.arg == Compare.GT:
                tokenizer.convert1(VMOp.GT, self)
            elif self.instruction.arg == Compare.GE:
                tokenizer.convert1(VMOp.GTE, self)
            elif self.instruction.arg == Compare.LT:
                tokenizer.convert1(VMOp.LT, self)
            elif self.instruction.arg == Compare.LE:
                tokenizer.convert1(VMOp.LTE, self)
            elif self.instruction.arg == Compare.EQ:
                tokenizer.convert1(VMOp.NUMEQUAL, self)
            elif self.instruction.arg == Compare.IS:
                tokenizer.convert1(VMOp.EQUAL, self)
            elif self.instruction.arg in [Compare.NE, Compare.IS_NOT]:
                tokenizer.convert1(VMOp.NUMNOTEQUAL, self)

        # arrays
        elif op == pyop.BUILD_LIST:
            tokenizer.convert_new_array(self)
        elif op == pyop.DUP_TOP:
            tokenizer.convert1(VMOp.DUP, self)
        elif op == pyop.YIELD_VALUE:
            tokenizer.convert1(VMOp.REVERSE, self)
        elif op == pyop.STORE_SUBSCR:
            tokenizer.convert_store_subscr(self)
#            tokenizer.convert1(VMOp.SETITEM,self)
        elif op == pyop.SETITEM:
            tokenizer.convert_set_element(self, self.instruction.arg)
#                tokenizer.convert1(VMOp.SETITEM,self, data=self.instruction.arg)
        elif op == pyop.STORE_SUBSCR:
            # this wont occur because this op is preprocessed into a SETITEM op
            pass
        elif op == pyop.BINARY_SUBSCR:
            tokenizer.convert1(VMOp.PICKITEM, self)

        elif op == pyop.BUILD_SLICE:
            tokenizer.convert_build_slice(self)

        # objects

        elif op == pyop.LOAD_CLASS_ATTR:
            tokenizer.convert_load_attr(self)

        elif op == pyop.STORE_ATTR:
            tokenizer.convert_store_attr(self)

        elif op == pyop.CALL_FUNCTION:
            tokenizer.convert_method_call(self)

#        elif op == pyop.POP_TOP:
#            if prev_token.func_name not in NON_RETURN_SYS_CALLS:
#                is_action = False
#                for item in tokenizer.method.module.actions:
#                    if item.method_name == prev_token.func_name:
#                        is_action = True
#
#                if not is_action:
#                    tokenizer.convert1(VMOp.DROP, self)
        else:
            print("OP NOT CONVERTED %s " % op)



