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

        if(num <= 1329) {
            return base_reward;
        }

        if(num == 1337){
            return 1337;
        }

        if(num == 1538){
            return 15380;
        }

        double m = 1;

        if(num % 10000 == 0){
            m = 6;
        } else if(num % 1000 == 0){
            m = 3;
        } else if(num % 100 == 0){
            m = 1.5;
        }

        if(num % 93 == 0 && num % 16 == 0 && num / 93 == 16){
            m = 0;
        }

        const double x = pow(num, 3) / pow(nonce, 2);
        return m * ceil(b * sin(i * x) + p * cos(k * x) + pow(e, i));
    }
}
