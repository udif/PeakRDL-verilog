import os

import jinja2 as jj
from systemrdl.node import RootNode, Node, RegNode, AddrmapNode, RegfileNode
from systemrdl.node import FieldNode, MemNode, AddressableNode
from systemrdl.rdltypes import AccessType, OnReadType, OnWriteType
#from systemrdl import RDLWalker

class VerilogExporter:

    def __init__(self, **kwargs):
        """
        Constructor for the Verilog Exporter class

        Parameters
        ----------
        user_template_dir: str
            Path to a directory where user-defined template overrides are stored.
        user_template_context: dict
            Additional context variables to load into the template namespace.
        """
        user_template_dir = kwargs.pop("user_template_dir", None)
        self.user_template_context = kwargs.pop("user_template_context", dict())

        # Check for stray kwargs
        if kwargs:
            raise TypeError("got an unexpected keyword argument '%s'" % list(kwargs.keys())[0])

        if user_template_dir:
            loader = jj.ChoiceLoader([
                jj.FileSystemLoader(user_template_dir),
                jj.FileSystemLoader(os.path.join(os.path.dirname(__file__), "templates")),
                jj.PrefixLoader({
                    'user': jj.FileSystemLoader(user_template_dir),
                    'base': jj.FileSystemLoader(os.path.join(os.path.dirname(__file__), "templates"))
                }, delimiter=":")
            ])
        else:
            loader = jj.ChoiceLoader([
                jj.FileSystemLoader(os.path.join(os.path.dirname(__file__), "templates")),
                jj.PrefixLoader({
                    'base': jj.FileSystemLoader(os.path.join(os.path.dirname(__file__), "templates"))
                }, delimiter=":")
            ])

        self.jj_env = jj.Environment(
            loader=loader,
            undefined=jj.StrictUndefined
        )

        # Define variables used during export
        RegNode.add_derived_property(self.bit_range)
        RegNode.add_derived_property(self.signal_prefix)
        FieldNode.add_derived_property(self.is_hw_writable)
        FieldNode.add_derived_property(self.is_hw_readable)
        FieldNode.add_derived_property(self.bit_range)
        FieldNode.add_derived_property(self.signal_prefix)

        # Top-level node
        self.top = None

        # Dictionary of group-like nodes (addrmap, regfile) and their bus
        # widths.
        # key = node path
        # value = max accesswidth/memwidth used in node's descendants
        self.bus_width_db = {}

        # Dictionary of root-level type definitions
        # key = definition type name
        # value = representative object
        #   components, this is the original_def (which can be None in some cases)
        self.namespace_db = {}


    def export(self, node: Node, path: str, **kwargs):
        """
        Perform the export!

        Parameters
        ----------
        node: systemrdl.Node
            Top-level node to export. Can be the top-level `RootNode` or any
            internal `AddrmapNode`.
        path: str
            Output file.
        example: bool
            If True (Default), Verilog register model is exported as a SystemVerilog
            package. Package name is based on the output file name.

            If False, register model is exported as an includable header.
        """
        #example_arg = kwargs.pop("example_arg", True)

        # Check for stray kwargs
        if kwargs:
            raise TypeError("got an unexpected keyword argument '%s'" % list(kwargs.keys())[0])

        # If it is the root node, skip to top addrmap
        if isinstance(node, RootNode):
            node = node.top


        # go through top level regfiles
        #modules = []
        #for desc in node.descendants():
        #    if (isinstance(desc, RegfileNode) and
        #        isinstance(desc.parent, AddrmapNode)):
        #        print(self._get_inst_name(desc))
        #        modules.append(desc);
        #node = modules[0]
        self.top = node

        # First, traverse the model and collect some information
        #self.bus_width_db = {}
        #RDLWalker().walk(self.top)

        context = {
            'print': print,
            'type': type,
            'top_node': node,
            'FieldNode': FieldNode,
            'RegNode': RegNode,
            'RegfileNode': RegfileNode,
            'AddrmapNode': AddrmapNode,
            'MemNode': MemNode,
            'AddressableNode': AddressableNode,
            'OnWriteType': OnWriteType,
            'isinstance': isinstance,
            'signal': self._get_signal_prefix,
            'get_inst_name': self._get_inst_name,
            'get_field_access': self._get_field_access,
            'get_array_address_offset_expr': self._get_array_address_offset_expr,
            'get_bus_width': self._get_bus_width,
            'get_mem_access': self._get_mem_access,
            'roundup_to': self._roundup_to,
            'roundup_pow2': self._roundup_pow2,
        }

        context.update(self.user_template_context)

        template = self.jj_env.get_template("module.sv")
        stream = template.stream(context)
        stream.dump(path)
        print("All done")


    def _get_inst_name(self, node: Node) -> str:
        """
        Returns the class instance name
        """
        return node.inst_name


    def _get_field_access(self, field: FieldNode) -> str:
        """
        Get field's Verilog access string
        """
        sw = field.get_property("sw")
        onread = field.get_property("onread")
        onwrite = field.get_property("onwrite")

        if sw == AccessType.rw:
            if (onwrite is None) and (onread is None):
                return "RW"
            elif (onread == OnReadType.rclr) and (onwrite == OnWriteType.woset):
                return "W1SRC"
            elif (onread == OnReadType.rclr) and (onwrite == OnWriteType.wzs):
                return "W0SRC"
            elif (onread == OnReadType.rclr) and (onwrite == OnWriteType.wset):
                return "WSRC"
            elif (onread == OnReadType.rset) and (onwrite == OnWriteType.woclr):
                return "W1CRS"
            elif (onread == OnReadType.rset) and (onwrite == OnWriteType.wzc):
                return "W0CRS"
            elif (onread == OnReadType.rset) and (onwrite == OnWriteType.wclr):
                return "WCRS"
            elif onwrite == OnWriteType.woclr:
                return "W1C"
            elif onwrite == OnWriteType.woset:
                return "W1S"
            elif onwrite == OnWriteType.wot:
                return "W1T"
            elif onwrite == OnWriteType.wzc:
                return "W0C"
            elif onwrite == OnWriteType.wzs:
                return "W0S"
            elif onwrite == OnWriteType.wzt:
                return "W0T"
            elif onwrite == OnWriteType.wclr:
                return "WC"
            elif onwrite == OnWriteType.wset:
                return "WS"
            elif onread == OnReadType.rclr:
                return "WRC"
            elif onread == OnReadType.rset:
                return "WRS"
            else:
                return "RW"

        elif sw == AccessType.r:
            if onread is None:
                return "RO"
            elif onread == OnReadType.rclr:
                return "RC"
            elif onread == OnReadType.rset:
                return "RS"
            else:
                return "RO"

        elif sw == AccessType.w:
            if onwrite is None:
                return "WO"
            elif onwrite == OnWriteType.wclr:
                return "WOC"
            elif onwrite == OnWriteType.wset:
                return "WOS"
            else:
                return "WO"

        elif sw == AccessType.rw1:
            return "W1"

        elif sw == AccessType.w1:
            return "WO1"

        else: # na
            return "NOACCESS"


    def _get_mem_access(self, mem: MemNode) -> str:
        sw = mem.get_property("sw")
        if sw == AccessType.r:
            return "R"
        else:
            return "RW"


    def _get_array_address_offset_expr(self, node: AddressableNode) -> str:
        """
        Returns an expression to calculate the address offset
        for example, a 4-dimensional array allocated as:
            [A][B][C][D] @ X += Y
        results in:
            X + i0*B*C*D*Y + i1*C*D*Y + i2*D*Y + i3*Y
        """
        s = "'h%x" % node.raw_address_offset
        if node.is_array:
            for i in range(len(node.array_dimensions)):
                m = node.array_stride
                for j in range(i+1, len(node.array_dimensions)):
                    m *= node.array_dimensions[j]
                s += " + i%d*'h%x" % (i, m)
        return s


    def _get_signal_prefix(self, node: Node) -> str:
        """
        Returns unique-in-addrmap prefix for signals
        """
        return node.get_rel_path(node.owning_addrmap,'','_','_','')


    def _get_bus_width(self, node: Node) -> int:
        """
        Returns group-like node's bus width (in bytes)
        """
        width = self.bus_width_db[node.get_path()]

        # Divide by 8, rounded up
        if width % 8:
            return width // 8 + 1
        else:
            return width // 8


    def _roundup_to(self, x: int, n: int) -> int:
        """
        Round x up to the nearest n
        """
        if x % n:
            return (x//n + 1) * n
        else:
            return (x//n) * n


    def _roundup_pow2(self, x):
        return 1<<(x-1).bit_length()


    def signal_prefix(self, node: Node) -> str:
        """
        Returns unique-in-addrmap prefix for signals
        """
        return node.get_rel_path(node.owning_addrmap,'','_','_','')


    def is_hw_writable(self, node) -> bool:
        """
        Field is writable by hardware
        """
        hw = node.get_property('hw')

        return hw in (AccessType.rw, AccessType.rw1,
                        AccessType.w, AccessType.w1)


    def is_hw_readable(self, node) -> bool:
        """
        Field is writable by hardware
        """
        hw = node.get_property('hw')

        return hw in (AccessType.rw, AccessType.rw1,
                        AccessType.r)


    def bit_range(self, node, fmt='{msb:2}:{lsb:2}') -> bool:
        """
        Formatted bit range for field
        """
        if type(node) == RegNode:
            return fmt.format(lsb=0, msb=node.size*8-1)
        else:
            return fmt.format(lsb=node.lsb, msb=node.msb)
