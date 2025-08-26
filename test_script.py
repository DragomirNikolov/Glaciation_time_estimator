i=0
c=0
while True:
    i=1 if i%2 == 0 else 0
    c+=1
    if c%1e8==0:
        print("100 000 000 iterations")