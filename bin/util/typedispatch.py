__all__ = ['TypeDispatcher', 'defaultdispatch', 'dispatch',
           'TypeDispatchError', 'TypeDispatchDeclarationError']

import inspect

def dispatch(*types):
	def dispatchF(f):
		def dispatchWrap(*args, **kargs):
			return f(*args, **kargs)
		dispatchWrap.__original__ = f
		dispatchWrap.__dispatch__ = types
		return dispatchWrap
	return dispatchF


def defaultdispatch(f):
	def defaultWrap(*args, **kargs):
		return f(*args, **kargs)
	defaultWrap.__original__ = f
	defaultWrap.__dispatch__ = (None,)
	return defaultWrap


def dispatch__call__(self, p, *args):
	t = type(p)
	table = self.__typeDispatchTable__

	func = table.get(t)
	
	if func is None:
		if not self.__concrete__:
			# Search for a matching superclass
			# This is slightly inefficient, as it will check the concrete class again.
			# On the other hand, this inefficiency will occur only once per class.
			for supercls in t.mro():
				func = table.get(supercls)
				if func is not None: break
				
		if func is None:
			func = table.get(None) # default

		# Cache the function that we found
		table[t] = func

	return func(self, p, *args)


class TypeDispatchError(Exception):
	pass

class TypeDispatchDeclarationError(Exception):
	pass


def exceptionDefault(self, node, *args):
	raise TypeDispatchError, "%r cannot handle %r\n%r" % (type(self), type(node), node)


def inlineAncestor(t, lut):
	if hasattr(t, '__typeDispatchTable__'):
		# Search for types that haven't been defined, yet.
		for k, v in t.__typeDispatchTable__.iteritems():
			if k not in lut:
				lut[k] = v

class typedispatcher(type):
	def __new__(self, name, bases, d):
		lut = {}
		restore = {}

		# Build the type lookup table from the local declaration
		for k, v in d.iteritems():
			if hasattr(v, '__dispatch__') and hasattr(v, '__original__'):
				types = v.__dispatch__
				original = v.__original__

				for t in types:
					if t in lut:
						raise TypeDispatchDeclarationError, "%s has declared with multiple handlers for type %s" % (name, t.__name__)
					else:
						lut[t] = original

				restore[k] = original

		# Remove the wrappers from the methods
		d.update(restore)

		# Search and inline dispatch tables from the MRO
		for base in bases:
			for t in inspect.getmro(base):
				inlineAncestor(t, lut)

		if None not in lut:
			raise TypeDispatchDeclarationError, "%s has no default dispatch" % (name,)

		d['__typeDispatchTable__'] = lut

		return type.__new__(self, name, bases, d)

class TypeDispatcher(object):
	__metaclass__    = typedispatcher
	__dispatch__     = dispatch__call__
	__call__         = dispatch__call__
	exceptionDefault = defaultdispatch(exceptionDefault)
	__concrete__ = False
