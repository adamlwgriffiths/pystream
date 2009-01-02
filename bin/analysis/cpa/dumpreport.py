from util.xmloutput  import XMLOutput
from common import simplecodegen

import os.path
from util import assureDirectoryExists

from programIR.python.ast import isPythonAST
import programIR.python.ast as ast
import programIR.python.program as program

from . import base

from . import programculler

import config

class LinkManager(object):
	def __init__(self):
		self.functionFile = {}
		self.objectFile = {}
		self.contextName = {}

		self.cid = 0
		
	def contextRef(self, context):
		if not context in self.contextName:
			self.contextName[context] = "c%d" % self.cid
			self.cid += 1
			assert context in self.contextName
		return self.contextName[context]

	def objectRef(self, obj):
		if isinstance(obj, program.AbstractObject):
			if obj not in self.objectFile: return None
			return self.objectFile[obj]
		else:
			if obj.obj not in self.objectFile: return None

			fn = self.objectFile[obj.obj]
			cn = self.contextRef(obj.context)
			return "%s#%s" % (fn, cn)

	def functionRef(self, obj):
		if isinstance(obj, ast.Function) or obj is None:
			if obj not in self.functionFile: return None
			return self.functionFile[obj]
		else:
			if obj.func not in self.functionFile: return None
			fn = self.functionFile[obj.func]
			cn = self.contextRef(obj.context)
			return "%s#%s" % (fn, cn)

class ContextFunction(object):
	__slots__ = 'context', 'func'
	def __init__(self, context, func):
		self.context = context
		self.func = func

def functionShortName(out, func, links=None, context = None):
	if isinstance(func, str):
		name = func
		args = []
		vargs = None
		kargs = None
	elif func is None:
		name = 'external'
		args = []
		vargs = None
		kargs = None
	else:
		name = func.name
		args = list(func.code.parameternames)
		vargs = None if func.code.vparam is None else func.code.vparam.name
		kargs = None if func.code.kparam is None else func.code.kparam.name

	if vargs is not None: args.append("*"+vargs)
	if kargs is not None: args.append("**"+kargs)


	if links is not None:
		if context is not None:
			link = links.functionRef(ContextFunction(context, func))
		else:
			link = links.functionRef(func)
	else:
		link = None

		
	if link: out.begin('a', href=link)
	out << "%s(%s)" % (name, ", ".join(args))
	if link: out.end('a')


def heapShortName(out, heap, links=None):
	if links != None:
		link = links.objectRef(heap)
	else:
		link = None
	
	if link:
		out.begin('a', href=link)
	out << repr(heap)
	if link:
		out.end('a')

def heapLink(out, heap, links=None):
	if links != None:
		link = links.objectRef(heap)
	else:
		link = None
	
	if link:
		out.begin('a', href=link)
	out << repr(heap)
	if link:
		out.end('a')


class TypeInferenceData(object):
	def liveFunctions(self):
		raise NotImplemented

	def liveHeap(self):
		raise NotImplemented

	def heapContexts(self, heap):
		raise NotImplemented

	def heapContextSlots(self, heapC):
		raise NotImplemented

	def heapContextSlot(self, slot):
		raise NotImplemented





def makeReportDirectory(moduleName):
	reportdir = os.path.join(config.outputDirectory, moduleName)
	assureDirectoryExists(reportdir)

	return reportdir

def makeOutput(reportDir, filename):
	fullpath = os.path.join(reportDir, filename)
	fout = open(fullpath, 'w')
	out = XMLOutput(fout)
	scg = simplecodegen.SimpleCodeGen(out) # HACK?
	return out, scg

def dumpHeader(out):
	out << "["
	out.begin('a', href="function_index.html")
	out << "Functions"
	out.end('a')
	out << " | "
	out.begin('a', href="object_index.html")
	out << "Objects"
	out.end('a')
	out << "]"
	out.tag('br')


def dumpFunctionInfo(func, data, links, out, scg):
	out.begin('h3')
	functionShortName(out, func)
	out.end('h3')

	info = data.db.functionInfo(func)
	funcOps = data.adb.functionOps(func)
	funcLocals = data.adb.functionLocals(func)

	if info.descriptive:
		out.begin('p')
		out.begin('b')
		out << 'descriptive'
		out.end('b')
		out.end('p')


	if func is not None:
		out.begin('pre')
		scg.walk(func)
		out.end('pre')


	numContexts = len(data.functionContexts(func))


	out.begin('p')
	out.begin('b')
	out << '%d contexts' % numContexts
	out.end('b')
	out.end('p')


	for context in data.functionContexts(func):
		out.tag('hr')
		
		cref = links.contextRef(context)
		out.tag('a', name=cref)
		
		out.begin('p')
		out << context
		out.end('p')
		out.endl()
		out.endl()

		def tableRow(label, *args):
			first = True
			out.begin('tr')
			out.begin('td')
			out.begin('b')
			out << label
			out.end('b')
			out.end('td')
			out.begin('td')

			for arg in args:
				if not first:
					out.tag('br')
				obj = arg.obj
				link = links.objectRef(arg)
				if link: out.begin('a', href=link)
				out << arg
				if link: out.end('a')

				first = False

			out.end('td')
			out.end('tr')
			out.endl()

		# HACK should pull from function information and contextualize
		if isinstance(context, base.CPAContext):
			out.begin('p')
			out.begin('table')

			if context.selfparam is not None:
				tableRow('self', context.selfparam)

			for arg in context.params:
				tableRow('param', arg)

			if context.vparamObj is not None:
				tableRow('vparams', context.vparamObj)

			if context.kparamObj is not None:
				tableRow('kparams', context.kparamObj)

			returnSlot = func.code.returnparam
			values = info.localInfo(returnSlot).context(context).references
			tableRow('return', *values)

			out.end('table')
			out.end('p')
			out.endl()
			out.endl()

		ops  = []
		lcls = []
		other = []
		
		for slot in data.functionContextSlots(func, context):
			if isinstance(slot.local, ast.Local):
				lcls.append(slot)
			elif isinstance(slot.local, program.AbstractObject):
				other.append(slot)
			else:
				ops.append(slot)

		def printTabbed(name, values):
			out << '\t'
			out << name
			out.endl()

			for value in values:
				out << '\t\t'				
				link = links.objectRef(value)
				if link: out.begin('a', href=link)
				out << value
				if link: out.end('a')
				out.endl()	


		out.begin('pre')
		for op in funcOps:
			printTabbed(op, info.opInfo(op).context(context).references)

			read, modify = data.db.lifetime.db[func][op][context]

			# HACK?
			if read or modify:
				out << '\t\t'
				out.begin('i')
				if read: out << "R"
				if modify: out << "M"
				out.end('i')
				out.endl()
		
		out.endl()

		for lcl in funcLocals:
			printTabbed(lcl, info.localInfo(lcl).context(context).references)
		out.end('pre')
		out.endl()


		out.begin('h3')
		out << "Callers"
		out.end('h3')
		out.begin('p')
		out.begin('ul')
		for callerF, callerC in data.callers(func, context):
			out.begin('li')
			functionShortName(out, callerF, links, callerC)
			out.end('li')
		out.end('ul')
		out.end('p')


		out.begin('h3')
		out << "Callees"
		out.end('h3')
		out.begin('p')
		out.begin('ul')
		for callerF, callerC in data.callees(func, context):
			out.begin('li')
			functionShortName(out, callerF, links, callerC)
			out.end('li')
		out.end('ul')
		out.end('p')


		live = data.db.lifetime.live[(func, context)]
		killed = data.db.lifetime.contextKilled[(func, context)]

		if live:
			out.begin('h3')
			out << "Live"
			out.end('h3')
			out.begin('p')
			out.begin('ul')
			for obj in live:
				out.begin('li')
				heapLink(out, obj, links)
				if obj in killed:
					out << " (killed)"
				out.end('li')
			out.end('ul')
			out.end('p')

		
		#reads = data.inter.la.rm.contextReads[context]
		reads = data.funcReads[func][context]

		if reads:
			out.begin('h3')
			out << "Reads"
			out.end('h3')
			out.begin('p')
			out.begin('ul')
			for obj in reads:
				out.begin('li')
				heapLink(out, obj, links)
				out.end('li')
			out.end('ul')
			out.end('p')


		#modifies = data.inter.la.rm.contextModifies[context]
		modifies = data.funcModifies[func][context]

		if modifies:
			out.begin('h3')
			out << "Modifies"
			out.end('h3')
			out.begin('p')
			out.begin('ul')
			for obj in modifies:
				out.begin('li')
				heapLink(out, obj, links)
				out.end('li')
			out.end('ul')
			out.end('p')

def dumpHeapInfo(heap, data, links, out):
	out.begin('h3')
	heapShortName(out, heap)
	out.end('h3')
	out.endl()

	heapInfo = data.db.heapInfo(heap)
	contexts = heapInfo.contexts

	la = data.db.lifetime

	out.begin('pre')

	for context in contexts:
		cref = links.contextRef(context)
		out.tag('a', name=cref)

		out << '\t'+str(context)+ '\n'

		for (slottype, key), info in heapInfo.slotInfos.iteritems():
			values = info.context(context).references
			if values:
				out << '\t\t%s / %s\n' % (str(slottype), str(key))
				for value in values:
					out << '\t\t\t'
					heapLink(out, value, links)
					out.endl()

		# HACK no easy way to get the context object, anymore?
##		info = la.getObjectInfo(contextobj)
##
##		if info.heldByClosure:
##			out << '\t\tHeld by (closure)\n'
##			for holder in info.heldByClosure:
##				out << '\t\t\t'
##				heapLink(out, holder.obj, links)
##				out.endl()
		out.endl()

	out.end('pre')

import util.graphalgorithim.dominator

def makeFunctionTree(data):
	liveFunctions = data.liveFunctions()

	head = None
	invokes = {}
	for func in liveFunctions:
		info = data.db.functionInfo(func)

		invokes[func] = set()

		for opinfo in info.opInfos.itervalues():
			for dstc, dstf in opinfo.merged.invokes:
				invokes[func].add(dstf)

	util.graphalgorithim.dominator.makeSingleHead(invokes, head)
	tree = util.graphalgorithim.dominator.dominatorTree(invokes, head)
	return tree, head


def makeHeapTree(data):
	liveHeap= data.liveHeap()

	head = None
	points = {}
	for heap in liveHeap:
		heapInfo = data.db.heapInfo(heap)

		points[heap] = set()

		for (slottype, key), info in heapInfo.slotInfos.iteritems():
			values = info.merged.references
			for dst in values:
				points[heap].add(dst.obj)

	util.graphalgorithim.dominator.makeSingleHead(points, head)
	tree = util.graphalgorithim.dominator.dominatorTree(points, head)
	return tree, head

def dumpReport(data, entryPoints):
	reportDir = makeReportDirectory('cpa')

	liveHeap = data.liveHeap()

	heapToFile = {}
	uid = 0

	links = LinkManager()

	for heap in liveHeap:
		fn = "h%07d.html" % uid
		links.objectFile[heap] = fn
		heapToFile[heap] = fn
		uid += 1


	liveFunctions, liveInvocations = programculler.findLiveFunctions(data.db, entryPoints)

	#liveFunctions = data.liveFunctions()

	funcToFile = {}
	uid = 0

	for func in liveFunctions:
		fn = "f%07d.html" % uid
		links.functionFile[func] = fn
		funcToFile[func] = fn
		uid += 1



	out, scg = makeOutput(reportDir, 'function_index.html')
	dumpHeader(out)

	out.begin('h2')
	out << "Function Index"
	out.end('h2')
	

	#tree, head = makeFunctionTree(data)

	head =  None
	tree = util.graphalgorithim.dominator.dominatorTree(liveInvocations, head)

	def printChildren(node):
		children = tree.get(node)
		if children:
			out.begin('ul')
			for func in children:
				out.begin('li')
				functionShortName(out, func, links)
				printChildren(func)
				out.end('li')
			out.end('ul')
			out.endl() 	
			
	printChildren(head)


##	out.begin('ul')
##	for func in liveFunctions:
##		out.begin('li')
##		functionShortName(out, func, links)
##		out.end('li')
##	out.end('ul')
##	out.endl()


	out, scg = makeOutput(reportDir, 'object_index.html')
	dumpHeader(out)

	out.begin('h2')
	out << "Object Index"
	out.end('h2')


	tree, head = makeHeapTree(data)
	nodes = set()
	def printHeapChildren(node):
		count = 0
		children = tree.get(node)
		if children:
			out.begin('ul')
			for heap in children:
				out.begin('li')
				link = links.objectRef(heap)
				if link: out.begin('a', href=link)
				out << heap
				nodes.add(heap)
				if link: out.end('a')
				count += printHeapChildren(heap) + 1
				out.end('li')
			out.end('ul')
			out.endl()
		return count
			
	count = printHeapChildren(head)

	if count != len(liveHeap):
		print "WARNING: tree contains %d elements, whereas there are %d expected." % (count, len(liveHeap))

##	print "Extra"
##	for node in nodes-set(liveHeap):
##		print node
##	print
	
	print "Missing"
	for node in set(liveHeap)-nodes:
		print node
	print


##	out.begin('ul')
##	for heap in liveHeap:
##		out.begin('li')
##		out.begin('a', href=links.objectRef(heap))
##		out << heap
##		out.end('a')
##		out.end('li')
##	out.end('ul')
##	out.endl() 	

	out.close()

	for func in liveFunctions:
		out, scg = makeOutput(reportDir, funcToFile[func])
		dumpHeader(out)
		dumpFunctionInfo(func, data, links, out, scg)
		out.endl() 	
		out.close()


	for heap in liveHeap:
		out, scg = makeOutput(reportDir, heapToFile[heap])
		dumpHeader(out)
		dumpHeapInfo(heap, data, links, out)
		out.endl() 	
		out.close()


	

