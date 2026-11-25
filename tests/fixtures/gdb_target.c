/* Debuggee for the GDB/MI integration tests. It is a test fixture, not a supported language. */
#include <stdio.h>

static int square(int v)
{
    int result = v * v; /* @bp-square */
    return result;      /* @bp-return */
}

int main(void)
{
    int total = 0;
    for (int i = 1; i <= 3; i++) {
        total += square(i);
    }
    printf("total=%d\n", total);
    return 0;
}
