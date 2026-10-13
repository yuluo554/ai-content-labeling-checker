"""确定性随机数（splitmix64）。

**为什么不用 stdlib ``random``**：标准库不承诺跨版本序列一致，而合成样本生成器
必须做到"任意机器、任意 Python 版本、固定 seed → 逐字节相同产物"（plan/05 §三.1）。

splitmix64 是公开的、实现只有几行的确定性算法（Vigna, 2015），输出序列在任何
平台上完全一致，是字节冻结型生成器的可靠基座。
"""

_MASK64 = (1 << 64) - 1

#: splitmix64 对 seed=0 的金标准前 8 项（守门测试逐值比对，见 plan/04 §十）。
#: 该序列与公开的 splitmix64 参考实现一致（前 5 项为社区公认值）。
GOLDEN_SEED0 = (
    0xE220A8397B1DCDAF,
    0x6E789E6AA1B965F4,
    0x06C45D188009454F,
    0xF88BB8A8724C81EC,
    0x1B39896A51A8749B,
    0x53CB9F0C747EA2EA,
    0x2C829ABE1F4532E1,
    0xC584133AC916AB3C,
)


class SplitMix64(object):
    """确定性 64 位 PRNG。

    用法::

        rng = SplitMix64(seed=42)
        rng.next_u64()          # 确定性的 64 位无符号整数
        rng.randbelow(10)       # [0, 10) 均匀整数
        rng.choice(["a", "b"])  # 列表元素（列表顺序敏感，确定性）
    """

    __slots__ = ("_state",)

    def __init__(self, seed=0):
        if not isinstance(seed, int):
            raise TypeError("seed 必须是整数，得到 {0!r}".format(type(seed).__name__))
        self._state = seed & _MASK64

    def next_u64(self):
        """推进状态并返回一个确定性的 64 位无符号整数。"""
        self._state = (self._state + 0x9E3779B97F4A7C15) & _MASK64
        z = self._state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _MASK64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _MASK64
        return (z ^ (z >> 31)) & _MASK64

    def randbelow(self, bound):
        """返回 ``[0, bound)`` 内的确定性整数（``bound`` 须为正）。"""
        if bound <= 0:
            raise ValueError("bound 必须为正整数，得到 {0}".format(bound))
        # 拒绝采样消除取模偏差；循环次数由确定性序列决定，可复现。
        limit = (1 << 64) - ((1 << 64) % bound)
        while True:
            value = self.next_u64()
            if value < limit:
                return value % bound

    def randint(self, low, high):
        """返回 ``[low, high]`` 内的确定性整数（闭区间）。"""
        if high < low:
            raise ValueError("high 必须 >= low")
        return low + self.randbelow(high - low + 1)

    def choice(self, seq):
        """从序列中确定性取一个元素（以序列顺序为输入，非 set）。"""
        if not seq:
            raise ValueError("choice() 不接受空序列")
        return seq[self.randbelow(len(seq))]

    def shuffle(self, seq):
        """Fisher–Yates 就地洗牌（确定性）。"""
        for i in range(len(seq) - 1, 0, -1):
            j = self.randbelow(i + 1)
            seq[i], seq[j] = seq[j], seq[i]
        return seq

    def sample(self, seq, k):
        """无放回取 k 个元素（确定性；不修改入参）。"""
        if k < 0 or k > len(seq):
            raise ValueError("k 越界：{0}（序列长度 {1}）".format(k, len(seq)))
        pool = list(seq)
        self.shuffle(pool)
        return pool[:k]


def derive_seed(master_seed, *parts):
    """由主种子与若干片段确定性派生子种子（用于多文件/多类目隔离）。

    片段按给定顺序混入，不使用 hash()（受 PYTHONHASHSEED 影响，不确定）。
    """
    value = master_seed & _MASK64
    for part in parts:
        text = str(part)
        for ch in text:
            value = (value * 0x100000001B3) & _MASK64  # FNV-1a 素数
            value ^= ord(ch)
        value = (value + 0x9E3779B97F4A7C15) & _MASK64
    return value


__all__ = ["SplitMix64", "derive_seed", "GOLDEN_SEED0"]
