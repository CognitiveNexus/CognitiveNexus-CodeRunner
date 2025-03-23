#include <stdio.h>
#include <stdlib.h>
#include <time.h>

typedef struct Node {
    int data;
    struct Node *next;
} Node;

Node* head = NULL;

void buildLinkedList() {
    Node *p = NULL;
    for(int i = 0; i < 3; i++) {
        p = malloc(sizeof(Node));
        p->data = rand() % 10;
        p->next = head->next;
        head->next = p;
    }
}

void printLinkedList() {
    Node *p = head;
    while(p->next) {
        p = p->next;
        printf("%d ", p->data);
    }
    printf("\nFinished.\n");
}

int main() {
    head = malloc(sizeof(Node));
    head->next = NULL;
    srand((unsigned)time(NULL));
    buildLinkedList();
    printLinkedList();
    return 0;
}