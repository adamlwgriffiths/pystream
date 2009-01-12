from __future__ import absolute_import

from . import expressions
from . import slots
from . import referencecount
from . import configuration
from . import secondary
from . import pathinformation

class CanonicalObjects(object):
	def __init__(self, ):
		self.localExprCache = {}
		self.fieldExprCache = {}
		
		self.localSlotCache = {}
		self.fieldSlotCache = {}

		self.configurationCache = {}

		self.rcm = referencecount.ReferenceCountManager()


	def configuration(self, type_, region, entry, current):
		key = (type_, region, entry, current)
		cache = self.configurationCache

		c = cache.get(key)
		if not c:
			c = configuration.Configuration(*key)
			cache[key] = c
		return c

	def paths(self, hits, misses):
		# Validate
		if hits:
			for hit in hits:
				assert hit.isExpression(), hit
		if misses:
			for miss in misses:
				assert miss.isExpression(), miss

		return pathinformation.PathInformation.fromHitMiss(hits, misses, self.fieldExpr)

	def secondary(self, paths, external):
		assert isinstance(external, bool)
		# TODO a non-copy create?
		return secondary.SecondaryInformation(paths.copy(), external)

	def localExpr(self, lcl):
		assert isinstance(lcl, slots.Slot), lcl

		key = lcl
		cache = self.localExprCache
		e = cache.get(key)
		if not e:
			e = expressions.LocalExpr(lcl)
			cache[key] = e
		return e

	def localSlot(self, lcl):
		assert not isinstance(lcl, slots.Slot), lcl
		key = lcl
		cache = self.localSlotCache
		e = cache.get(key)
		if not e:
			e = slots.LocalSlot(lcl)
			cache[key] = e
		return e

	def fieldExpr(self, expr, field):
		assert isinstance(expr, expressions.Expression), expr
		assert isinstance(field, slots.FieldSlot), field

		key = (expr, field)
		cache = self.fieldExprCache
		e = cache.get(key)
		if not e:
			e = expressions.FieldExpr(expr, field)
			cache[key] = e
		return e

	def fieldSlot(self, expr, field):
		assert not isinstance(expr, slots.Slot), expr
		assert not isinstance(field, slots.Slot), field

		key = (expr, field)
		cache = self.fieldSlotCache
		e = cache.get(key)
		if not e:
			e = slots.FieldSlot(expr, field)
			cache[key] = e
		return e
			

	def incrementRef(self, refs, slot):
		return self.rcm.increment(refs, slot)

	def decrementRef(self, refs, slot):
		return self.rcm.decrement(refs, slot)
