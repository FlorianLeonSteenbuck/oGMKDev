<?php
function add(int $a, int $b): int {
    $sum = $a + $b;
    return $sum; // @bp-return
}
$total = add(2, 3);
echo "total=$total\n";
