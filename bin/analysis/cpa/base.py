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

from language.python import program, ast

import util
import analysis.cpasignature
import util.python.calling
import util.canonical
CanonicalObject = util.canonical.CanonicalObject

from analysis.storegraph import extendedtypes
from analysis.storegraph import storegraph

###########################
### Evaluation Contexts ###
###########################

def localSlot(sys, code, lcl, context):
	if isinstance(lcl, ast.Local):
		assert isinstance(lcl, ast.Local), type(lcl)
		name = sys.canonical.localName(code, lcl, context)
		return context.group.root(name)
	elif isinstance(lcl, ast.DoNotCare):
		return analysis.cpasignature.DoNotCare
	elif lcl is None:
		return None
	else:
		assert False, type(lcl)

def calleeSlotsFromContext(sys, context):
	code = context.signature.code

	callee = code.codeParameters()

	selfparam   = localSlot(sys, code, callee.selfparam, context)
	parameters  = tuple([localSlot(sys, code, p, context) for p in callee.params])
	if callee.defaults:
		defaults = callee.defaults # HACK?
		#defualts = tuple([localSlot(sys, code, d, context) for d in callee.defaults])
	else:
		defaults    = ()
	vparam      = localSlot(sys, code, callee.vparam, context)
	kparam      = localSlot(sys, code, callee.kparam, context)
	returnparams = [localSlot(sys, code, param, context) for param in callee.returnparams]

	return util.python.calling.CalleeParams(selfparam, parameters,
		callee.paramnames, defaults, vparam, kparam, returnparams)


class AnalysisContext(CanonicalObject):
	__slots__ = 'signature', 'opPath', 'group'

	def __init__(self, signature, opPath, group):
		self.signature  = signature
		self.opPath     = opPath
		self.group      = group

		self.setCanonical(self.signature, self.opPath)

	def _bindObjToSlot(self, sys, obj, slot):
		assert not ((obj is None) ^ (slot is None)), (obj, slot)
		if obj is not None and slot is not None:
			assert isinstance(obj, extendedtypes.ExtendedType), type(obj)
			assert isinstance(slot, storegraph.SlotNode)

			slot.initializeType(obj)

	def vparamType(self, sys):
		return self._extendedParamType(sys, sys.tupleClass.typeinfo.abstractInstance)

	def _extendedParamType(self, sys, inst):
		# Extended param objects are named by the context they appear in.
		return sys.canonical.contextType(self, inst, None)


	def _vparamSlot(self, sys, vparamObj, index):
		slotName = sys.canonical.fieldName('Array', sys.extractor.getObject(index))
		field = vparamObj.field(slotName, self.group.regionHint)
		return field

	def invocationMaySucceed(self, sys):
		sig = self.signature
		callee = calleeSlotsFromContext(sys, self)

		# info is not actually intrinsic to the context?
		info = util.python.calling.callStackToParamsInfo(callee,
			sig.selfparam is not None, sig.numParams(),
			False, 0, False)

		if info.willSucceed.maybeFalse():
			if info.willSucceed.mustBeFalse():
				print "Call to %r will always fail." % self.signature
			else:
				print "Call to %r may fail." % self.signature

		return info.willSucceed.maybeTrue()

	def initializeVParam(self, sys, cop, vparamSlot, length):
		vparamType = self.vparamType(sys)

		# Set the varg pointer
		# Ensures the object node is created.
		self._bindObjToSlot(sys, vparamType, vparamSlot)

		vparamObj = vparamSlot.initializeType(vparamType)
		sys.logAllocation(cop, vparamObj) # Implicitly allocated

		# Set the length of the vparam tuple.
		lengthObjxtype  = sys.canonical.existingType(sys.extractor.getObject(length))
		lengthSlot = vparamObj.field(sys.storeGraph.lengthSlotName, self.group.regionHint)
		self._bindObjToSlot(sys, lengthObjxtype, lengthSlot)
		sys.logModify(cop, lengthSlot)

		return vparamObj


	def initalizeParameter(self, sys, param, cpaType, arg):
		if param is None:
			assert cpaType is None
			assert arg is None
		elif param is analysis.cpasignature.DoNotCare:
			pass
		elif cpaType is analysis.cpasignature.Any:
			assert isinstance(param, storegraph.SlotNode)
			assert isinstance(arg,   storegraph.SlotNode)
			sys.createAssign(arg, param)
		else:
			# TODO skip this if this context has already been bound
			# but for a different caller
			param.initializeType(cpaType)


	def bindParameters(self, sys, caller):
		sig = self.signature

		callee = calleeSlotsFromContext(sys, self)

		# Bind self parameter
		self.initalizeParameter(sys, callee.selfparam, sig.selfparam, caller.selfarg)

		# Bind the positional parameters
		numArgs  = len(sig.params)
		numParam = len(callee.params)

		for arg, cpaType, param in zip(caller.args[:numParam], sig.params[:numParam], callee.params):
			self.initalizeParameter(sys, param, cpaType, arg)

		#assert numArgs >= numParam
		# HACK bind defaults
		if numArgs < numParam:
			defaultOffset = len(callee.params)-len(callee.defaults)
			for i in range(numArgs, numParam):
				obj = callee.defaults[i-defaultOffset].object

				# Create an initialize an existing object
				name = sys.canonical.existingName(sig.code, obj, self)
				slot = self.group.root(name)
				slot.initializeType(sys.canonical.existingType(obj))

				# Transfer the default
				sys.createAssign(slot, callee.params[i])


		# An op context for implicit allocation
		cop = sys.canonical.opContext(sig.code, None, self)

		# Bind the vparams
		if callee.vparam is not None and callee.vparam is not analysis.cpasignature.DoNotCare:
			vparamObj = self.initializeVParam(sys, cop, callee.vparam, numArgs-numParam)

			# Bind the vargs
			for i in range(numParam, numArgs):
				arg     = caller.args[i]
				cpaType = sig.params[i]
				param = self._vparamSlot(sys, vparamObj, i-numParam)
				self.initalizeParameter(sys, param, cpaType, arg)
				sys.logModify(cop, param)

		else:
			pass #assert callee.vparam is not None or numArgs == numParam

		# Bind the kparams
		assert callee.kparam is None


		# Copy the return value
		if caller.returnargs is not None:
			assert len(callee.returnparams) == len(caller.returnargs)
			for param, arg in zip(callee.returnparams, caller.returnargs):
				sys.createAssign(param, arg)

	def isAnalysisContext(self):
		return True
