; demo.asm — primes up to 30 by trial division, then fib(20) by recursion.
          enter 3
          push 2
          store 0             ; n = 2
pl:       load 0
          push 30
          gt
          jnz pdone
          load 0
          call isprime
          jz nextn
          load 0
          print
nextn:    load 0
          push 1
          add
          store 0
          jmp pl
pdone:    push 20
          call fib            ; fib(20) = 6765
          print
          halt

; isprime(n) -> 1 when n is prime, else 0
isprime:  enter 2
          store 0             ; n
          push 2
          store 1             ; d = 2
ip:       load 1
          load 1
          mul
          load 0
          gt                  ; d*d > n ?
          jnz prime
          load 0
          load 1
          mod
          push 0
          eq                  ; n % d == 0 ?
          jnz notprime
          load 1
          push 1
          add
          store 1
          jmp ip
prime:    push 1
          ret
notprime: push 0
          ret

; fib(n) -> n < 2 ? n : fib(n-1) + fib(n-2)
fib:      enter 1
          store 0
          load 0
          push 2
          lt
          jz fr
          load 0
          ret
fr:       load 0
          push 1
          sub
          call fib
          load 0
          push 2
          sub
          call fib
          add
          ret
