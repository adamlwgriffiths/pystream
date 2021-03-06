# Copyright 2011 Nicholas Bray
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from util.typedispatch import *
from language.python import ast

class ReadModifyInfo(object):
	__slots__ = 'localRead', 'localModify', 'fieldRead', 'fieldModify'

	def __init__(self):
		self.localRead   = set()
		self.localModify = set()
		self.fieldRead   = set()
		self.fieldModify = set()

	def update(self, other):
		self.localRead.update(other.localRead)
		self.localModify.update(other.localModify)
		self.fieldRead.update(other.fieldRead)
		self.fieldModify.update(other.fieldModify)


class FindReadModify(TypeDispatcher):

	def getListInfo(self, l):
		info = ReadModifyInfo()
		for child in l:
			info.update(self(child))
		return info

	@dispatch(ast.Existing, ast.Code, ast.DoNotCare, ast.leafTypes)
	def visitLeaf(self, node, info):
		pass

	@dispatch(ast.Local)
	def visitLocal(self, node, info):
		info.localRead.add(node)

	@dispatch(ast.Allocate)
	def visitAllocate(self, node, info):
		# TODO what about type/field nullification?
		node.visitChildrenArgs(self, info)

	@dispatch(ast.Load, ast.Check)
	def visitMemoryExpr(self, node, info):
		node.visitChildrenArgs(self, info)
		info.fieldRead.update(node.annotation.reads[0])
		info.fieldModify.update(node.annotation.modifies[0])

	@dispatch(ast.Store)
	def visitStore(self, node):
		info = ReadModifyInfo()
		node.visitChildrenArgs(self, info)
		info.fieldRead.update(node.annotation.reads[0])
		info.fieldModify.update(node.annotation.modifies[0])
		self.lut[node] = info
		return info


	@dispatch(ast.DirectCall, ast.Call, ast.MethodCall)
	def visitDirectCall(self, node, info):
		node.visitChildrenArgs(self, info)
		info.fieldRead.update(node.annotation.reads[0])
		info.fieldModify.update(node.annotation.modifies[0])

	@dispatch(ast.Assign)
	def visitAssign(self, node):
		info = ReadModifyInfo()
		self(node.expr, info)
		info.localModify.update(node.lcls)
		self.lut[node] = info
		return info

	@dispatch(ast.Return)
	def visitReturn(self, node):
		info = ReadModifyInfo()
		self(node.exprs, info)
		self.lut[node] = info
		return info

	@dispatch(ast.Discard)
	def visitDiscard(self, node):
		info = ReadModifyInfo()
		self(node.expr, info)
		self.lut[node] = info
		return info

	@dispatch(list)
	def visitList(self, node, info):
		for child in node:
			self(child, info)

	@dispatch(ast.Suite)
	def visitSuite(self, node):
		info = self.getListInfo(node.blocks)
		self.lut[node] = info
		return info

	@dispatch(ast.For)
	def visitFor(self, node):
		info = ReadModifyInfo()
		info.update(self(node.loopPreamble))
		info.localRead.add(node.iterator)
		info.localModify.add(node.index)

		info.update(self(node.bodyPreamble))
		info.update(self(node.body))
		info.update(self(node.else_))

		self.lut[node] = info
		return info


	@dispatch(ast.Condition)
	def visitCondition(self, node):
		info = ReadModifyInfo()
		info.update(self(node.preamble))
		info.localRead.add(node.conditional)
		self.lut[node] = info
		return info


	@dispatch(ast.While)
	def visitWhile(self, node):
		info = ReadModifyInfo()
		info.update(self(node.condition))
		info.update(self(node.body))
		info.update(self(node.else_))
		self.lut[node] = info
		return info

	@dispatch(ast.Switch)
	def visitSwitch(self, node):
		info = ReadModifyInfo()
		info.update(self(node.condition))
		info.update(self(node.t))
		info.update(self(node.f))
		self.lut[node] = info
		return info

	@dispatch(ast.TypeSwitchCase)
	def visitTypeSwitchCase(self, node):
		info = ReadModifyInfo()
		info.localModify.add(node.expr)
		info.update(self(node.body))
		self.lut[node] = info
		return info

	@dispatch(ast.TypeSwitch)
	def visitTypeSwitch(self, node):
		info = ReadModifyInfo()

		info.localRead.add(node.conditional)
		for case in node.cases:
			info.update(self(case))

		self.lut[node] = info
		return info

	@dispatch(ast.OutputBlock)
	def visitOutputBlock(self, node):
		info = ReadModifyInfo()

		for output in node.outputs:
			self(output.expr, info)

		self.lut[node] = info
		return info

	def processCode(self, code):
		self.lut = {}
		self(code.ast)
		return self.lut
