int bit_mix(int x, int y) {
    int a = x ^ y;
    int b = (x & y) << 1;
    return a | b;
}

