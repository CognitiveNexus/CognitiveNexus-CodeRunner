#include <stdio.h>
#include <stdlib.h>
int main() {
    int a = 1, *b = &a, *c = NULL;
    *b = 114514;
    c = malloc(sizeof(int));
    *c = 1919810;
    printf("%d %d %d\n", a, *b, *c);
    return 0;
}