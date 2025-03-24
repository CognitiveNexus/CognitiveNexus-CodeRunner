#include <stdio.h>

struct {
    long lorem;
    double ipsum;
    struct {
        char foo;
        int bar;
    } dolor;
    union {
        char sit;
        int amet;
    };
} loremIpsum;

int main() {
    loremIpsum.lorem = 0L;
    loremIpsum.ipsum = 0.0;
    loremIpsum.dolor.foo = '0';
    loremIpsum.dolor.bar = 0;
    loremIpsum.sit = '\0';
    return loremIpsum.amet;
}