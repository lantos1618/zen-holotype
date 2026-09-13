#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifndef N
#define N 100000
#endif
#ifndef CASE
#define CASE 0
#endif
typedef struct { size_t key, index; } Item;
static void merge(Item *x, Item *tmp, size_t lo, size_t hi) {
    if (hi-lo<2) return;
    size_t mid=(lo+hi)/2;
    merge(x,tmp,lo,mid); merge(x,tmp,mid,hi);
    size_t l=lo,r=mid;
    for(size_t i=lo;i<hi;i++) tmp[i]=(l<mid && (r==hi || x[l].key<=x[r].key))?x[l++]:x[r++];
    memcpy(x+lo,tmp+lo,(hi-lo)*sizeof(Item));
}
int main(void) {
    size_t sum=0,n=N;
#if CASE == 0 || CASE == 4
    for(size_t i=0;i<n;i++) sum=(sum*33+i)%1000003;
#elif CASE == 1
    size_t *v=malloc(n*sizeof(size_t)), cap=16;
    while(cap*3<n*4) cap*=2;
    size_t *slots=calloc(cap,sizeof(size_t));
    for(size_t i=0;i<n;i++) {
        v[i]=i*3+7;
        size_t s=(UINT64_C(5381)*1000003+i)%cap;
        while(slots[s]) s=(s+1)%cap;
        slots[s]=i+1;
    }
    for(size_t j=n;j>0;j--) {
        size_t key=j-1,s=(UINT64_C(5381)*1000003+key)%cap;
        while(slots[s] && slots[s]-1!=key) s=(s+1)%cap;
        sum+=v[slots[s]-1];
    }
    free(slots); free(v);
#elif CASE == 2
    size_t cap=1,len=0; char *s=malloc(cap);
    for(size_t i=0;i<n;i++) {
        char digits[32]; int size=snprintf(digits,sizeof digits,"%zu:",i);
        if(len+(size_t)size>cap) {cap=(len+(size_t)size)*2;s=realloc(s,cap);}
        memcpy(s+len,digits,(size_t)size);len+=(size_t)size;
    }
    for(size_t i=0;i<len;i++) sum+=(unsigned char)s[i];
    free(s);
#elif CASE == 3
    Item *x=malloc(n*sizeof(Item)),*tmp=malloc(n*sizeof(Item));
    for(size_t i=0;i<n;i++) x[i]=(Item){(n-i)%257,i};
    merge(x,tmp,0,n);
    for(size_t i=0;i<n;i++) sum+=(i%97+1)*(x[i].key+x[i].index);
    free(tmp); free(x);
#endif
    printf("%zu\n",sum);
    return 0;
}
