#define ull unsigned long long

extern "C" {
ull reward_function(const ull base_reward, const ull height, const ull nonce) {
    return base_reward + height * 0 + nonce * 0;
}
}
