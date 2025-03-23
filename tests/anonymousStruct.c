#include <stdio.h>

struct {    
    char foo;
    int bar;
} fooBar;
struct {
    long lorem;
    double ipsum;
} loremIpsum;

int main() {
    fooBar.foo = '#';
    fooBar.bar = 114514;
    loremIpsum.lorem = 0L;
    loremIpsum.ipsum = 0.0;
    return loremIpsum.lorem + loremIpsum.ipsum;
}