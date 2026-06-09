# Makefile
CXX = g++
CXXFLAGS = $(shell root-config --cflags) -fPIC -I include
LDFLAGS  = $(shell root-config --glibs)

SRCS = $(wildcard src/*.cc)
OBJS = $(patsubst src/%.cc, obj/%.o, $(SRCS)) obj/Dict.o
LINKDEF = include/RawObjs/LinkDef.h
HEADERS = $(filter-out %LinkDef.h, $(wildcard include/RawObjs/*.hh))

libRawObjs.so: $(OBJS)
	$(CXX) -shared -o $@ $^ $(LDFLAGS)

Dict.cc: $(HEADERS) $(LINKDEF)
	rootcling -f $@ -I include $(HEADERS) $(LINKDEF)

obj/Dict.o: Dict.cc
	$(CXX) $(CXXFLAGS) -c -o $@ $<

obj/%.o: src/%.cc | obj
	$(CXX) $(CXXFLAGS) -c -o $@ $<

clean:
	rm -f obj/*.o libRawObjs.so Dict.cc Dict_rdict.pcm
