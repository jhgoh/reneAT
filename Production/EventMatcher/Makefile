# Makefile for EventMatcher
CXX = g++
CXXFLAGS = $(shell root-config --cflags) -fPIC -I include -I ../RawObjs/include
LDFLAGS  = $(shell root-config --glibs) -L../RawObjs -lRawObjs -Wl,-rpath,'$$ORIGIN/../RawObjs'

SRCS = $(wildcard src/*.cc)
OBJS = $(patsubst src/%.cc, obj/%.o, $(SRCS))

libEventMatcher.so: $(OBJS)
	$(CXX) -shared -o $@ $^ $(LDFLAGS)

obj/%.o: src/%.cc | obj
	$(CXX) $(CXXFLAGS) -c -o $@ $<

obj:
	mkdir -p obj

clean:
	rm -rf obj libEventMatcher.so
