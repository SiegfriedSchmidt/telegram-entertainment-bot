#include <cmath>
#define ull unsigned long long

using namespace std;

extern "C" {
    ull reward_function(const ull base_reward, const ull num, const ull nonce) {
        constexpr double b = 52;
        constexpr double i = 7.62;
        constexpr double p = 856;
        constexpr double k = 1.538;
        constexpr double e = 2.71828;

        if (num <= 1328) {
            return base_reward;
        }
        const double x = pow(num, 3) / pow(nonce, 2);
        return ceil(b * sin(i * x) + p * cos(k * x) + pow(e, i));
    }
}
