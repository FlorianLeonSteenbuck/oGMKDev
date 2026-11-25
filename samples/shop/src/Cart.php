<?php
final class Cart
{
    // TODO: total with tax
    public function total(array $lines): int
    {
        /* FIXME: array_sum ignores negative lines */
        return array_sum($lines);
    }
}
