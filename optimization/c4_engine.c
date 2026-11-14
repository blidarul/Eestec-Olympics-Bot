/*
 * Fast Bitboard Connect Four Negamax Engine.
 * Supports variable R (rows), C (cols), K (connect-in-a-row).
 * Built for Linux AMD64 and Windows MinGW with 128-bit bitboard support.
 * Owned by agent `bld`.
 */

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#ifdef _WIN32
#include <windows.h>
#define EXPORT __declspec(dllexport)
static inline double get_wall_time(void) {
    LARGE_INTEGER freq, count;
    QueryPerformanceFrequency(&freq);
    QueryPerformanceCounter(&count);
    return (double)count.QuadPart / (double)freq.QuadPart;
}
#else
#include <time.h>
#define EXPORT __attribute__((visibility("default")))
static inline double get_wall_time(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
}
#endif

typedef unsigned __int128 uint128;

#define MAX_COLS 16
#define TT_SIZE (1 << 21) // 2M entries ~ 48MB (<= 256MB)
#define TT_MASK (TT_SIZE - 1)

typedef struct {
    uint64_t key_cp;
    uint64_t key_mask;
    uint32_t key_hi;
    int16_t score;
    int8_t depth;
    uint8_t flag; // 0: EXACT, 1: UPPER, 2: LOWER
} TTEntry;

static TTEntry tt[TT_SIZE];
static int tt_initialized = 0;

static inline void clear_tt(void) {
    memset(tt, 0, sizeof(tt));
}

static inline int check_win(uint128 m, int S, int K) {
    // 1. Vertical (shift 1)
    uint128 v = m;
    for (int i = 0; i < K - 1; i++) {
        v &= (v >> 1);
    }
    if (v != 0) return 1;

    // 2. Horizontal (shift S)
    uint128 h = m;
    for (int i = 0; i < K - 1; i++) {
        h &= (h >> S);
    }
    if (h != 0) return 1;

    // 3. Diagonal / (up 1, right 1: shift S + 1)
    uint128 d1 = m;
    for (int i = 0; i < K - 1; i++) {
        d1 &= (d1 >> (S + 1));
    }
    if (d1 != 0) return 1;

    // 4. Diagonal \ (down 1, right 1: shift S - 1)
    uint128 d2 = m;
    for (int i = 0; i < K - 1; i++) {
        d2 &= (d2 >> (S - 1));
    }
    if (d2 != 0) return 1;

    return 0;
}

// Precomputed geometry per search call
static int g_R = 6, g_C = 7, g_K = 4, g_S = 7;
static uint128 g_col_masks[MAX_COLS];
static uint128 g_top_masks[MAX_COLS];
static uint128 g_bottom_bits[MAX_COLS];
static int g_center_order[MAX_COLS];
static int g_col_weights[MAX_COLS];
static double g_deadline = 0.0;
static int g_timeout_hit = 0;
static uint64_t g_nodes_searched = 0;

static inline int eval_heuristic(uint128 cur_p, uint128 opp_p) {
    int score = 0;
    for (int c = 0; c < g_C; c++) {
        uint128 cb = g_col_masks[c];
        int w = g_col_weights[c];
        uint64_t p_lo = (uint64_t)(cur_p & cb);
        uint64_t p_hi = (uint64_t)((cur_p & cb) >> 64);
        uint64_t o_lo = (uint64_t)(opp_p & cb);
        uint64_t o_hi = (uint64_t)((opp_p & cb) >> 64);

        int count_p = __builtin_popcountll(p_lo) + __builtin_popcountll(p_hi);
        int count_o = __builtin_popcountll(o_lo) + __builtin_popcountll(o_hi);
        score += (count_p - count_o) * w;
    }
    return score;
}

static int negamax(uint128 cp, uint128 mask, int depth, int alpha, int beta) {
    g_nodes_searched++;
    if ((g_nodes_searched & 4095) == 0) {
        if (get_wall_time() >= g_deadline) {
            g_timeout_hit = 1;
            return 0;
        }
    }

    if (depth <= 0) {
        return eval_heuristic(cp, mask ^ cp);
    }

    uint64_t k_cp = (uint64_t)cp;
    uint64_t k_m = (uint64_t)mask;
    uint32_t k_hi = (uint32_t)((cp >> 64) ^ ((mask >> 64) * 0x9e3779b97f4a7c15ULL));
    uint32_t tt_idx = (uint32_t)((k_cp * 0x9e3779b97f4a7c15ULL ^ k_m * 0xbf58476d1ce4e5b9ULL ^ k_hi) & TT_MASK);
    TTEntry *entry = &tt[tt_idx];

    if (entry->key_cp == k_cp && entry->key_mask == k_m && entry->key_hi == k_hi && entry->depth >= depth) {
        if (entry->flag == 0) return entry->score;
        if (entry->flag == 1 && entry->score <= alpha) return entry->score;
        if (entry->flag == 2 && entry->score >= beta) return entry->score;
    }

    int open_count = 0;
    int moves[MAX_COLS];
    for (int i = 0; i < g_C; i++) {
        int c = g_center_order[i];
        if (!(mask & g_top_masks[c])) {
            moves[open_count++] = c;
        }
    }

    if (open_count == 0) {
        return 0; // Board is completely full: draw
    }

    // 1. Immediate win check
    for (int i = 0; i < open_count; i++) {
        int c = moves[i];
        uint128 np = (mask + g_bottom_bits[c]) & g_col_masks[c];
        if (check_win(cp | np, g_S, g_K)) {
            return 10000 + depth;
        }
    }

    int best = -30000;
    int orig_alpha = alpha;
    uint128 next_opp = mask ^ cp;

    for (int i = 0; i < open_count; i++) {
        int c = moves[i];
        uint128 np = (mask + g_bottom_bits[c]) & g_col_masks[c];
        uint128 above = np << 1;

        int val;
        // Check if dropping here hands the opponent an immediate winning drop right above
        if ((above & g_col_masks[c]) && check_win(next_opp | above, g_S, g_K)) {
            val = -(9000 + depth);
        } else {
            val = -negamax(next_opp, mask | np, depth - 1, -beta, -alpha);
        }

        if (g_timeout_hit) return 0;

        if (val > best) best = val;
        if (val > alpha) alpha = val;
        if (alpha >= beta) break;
    }

    if (!g_timeout_hit) {
        entry->key_cp = k_cp;
        entry->key_mask = k_m;
        entry->key_hi = k_hi;
        entry->score = (int16_t)best;
        entry->depth = (int8_t)depth;
        if (best <= orig_alpha) entry->flag = 1;
        else if (best >= beta) entry->flag = 2;
        else entry->flag = 0;
    }

    return best;
}

EXPORT int c4_solve(
    int R, int C, int K,
    const int *moves, int num_moves,
    int one_indexed,
    int max_depth,
    double timeout_seconds,
    int *out_score, int *out_depth, int *out_proven
) {
    if (R > 14 || C > MAX_COLS || K < 3) {
        return -1;
    }

    g_R = R;
    g_C = C;
    g_K = K;
    g_S = R + 1;
    g_nodes_searched = 0;
    g_timeout_hit = 0;

    double t_start = get_wall_time();
    g_deadline = t_start + (timeout_seconds > 0.05 ? timeout_seconds : 8.0);

    for (int c = 0; c < C; c++) {
        g_col_masks[c] = ((((uint128)1) << R) - 1) << (c * g_S);
        g_top_masks[c] = ((uint128)1) << (c * g_S + R - 1);
        g_bottom_bits[c] = ((uint128)1) << (c * g_S);
        double dist = fabs((double)c - (double)(C - 1) / 2.0);
        g_col_weights[c] = (int)(10.0 * (1.0 - dist / ((double)C / 2.0))) + 1;
    }

    // Order columns by distance to center
    for (int i = 0; i < C; i++) g_center_order[i] = i;
    for (int i = 0; i < C - 1; i++) {
        for (int j = i + 1; j < C; j++) {
            double d_i = fabs((double)g_center_order[i] - (double)(C - 1) / 2.0);
            double d_j = fabs((double)g_center_order[j] - (double)(C - 1) / 2.0);
            if (d_j < d_i) {
                int tmp = g_center_order[i];
                g_center_order[i] = g_center_order[j];
                g_center_order[j] = tmp;
            }
        }
    }

    // Replay moves
    uint128 p0 = 0;
    uint128 mask = 0;
    int turn = 0;

    for (int i = 0; i < num_moves; i++) {
        int m = moves[i];
        if (one_indexed) m = m - 1;
        if (m < 0 || m >= C) continue;
        if (mask & g_top_masks[m]) continue; // full column

        uint128 np = (mask + g_bottom_bits[m]) & g_col_masks[m];
        if (turn == 0) p0 |= np;
        mask |= np;
        turn = 1 - turn;
    }

    uint128 cur_p = (turn == 0) ? p0 : (mask ^ p0);
    uint128 opp_p = mask ^ cur_p;

    int open_c[MAX_COLS];
    int open_count = 0;
    for (int i = 0; i < C; i++) {
        int c = g_center_order[i];
        if (!(mask & g_top_masks[c])) {
            open_c[open_count++] = c;
        }
    }

    if (open_count == 0) {
        if (out_score) *out_score = 0;
        if (out_depth) *out_depth = 0;
        if (out_proven) *out_proven = 1;
        return -1;
    }

    // 1. Immediate Win Check (1 ply)
    for (int i = 0; i < open_count; i++) {
        int c = open_c[i];
        uint128 np = (mask + g_bottom_bits[c]) & g_col_masks[c];
        if (check_win(cur_p | np, g_S, g_K)) {
            if (out_score) *out_score = 10000;
            if (out_depth) *out_depth = 1;
            if (out_proven) *out_proven = 1;
            return one_indexed ? (c + 1) : c;
        }
    }

    // 2. Immediate Block Check (1 ply)
    int blocks[MAX_COLS];
    int block_count = 0;
    for (int i = 0; i < open_count; i++) {
        int c = open_c[i];
        uint128 np = (mask + g_bottom_bits[c]) & g_col_masks[c];
        if (check_win(opp_p | np, g_S, g_K)) {
            blocks[block_count++] = c;
        }
    }

    if (block_count > 0) {
        int chosen_block = blocks[0];
        for (int i = 0; i < block_count; i++) {
            int b = blocks[i];
            uint128 np = (mask + g_bottom_bits[b]) & g_col_masks[b];
            uint128 above = np << 1;
            if (!((above & g_col_masks[b]) && check_win(opp_p | above, g_S, g_K))) {
                chosen_block = b;
                break;
            }
        }
        if (out_score) *out_score = -500;
        if (out_depth) *out_depth = 1;
        if (out_proven) *out_proven = 0;
        return one_indexed ? (chosen_block + 1) : chosen_block;
    }

    // 3. Iterative Deepening Negamax
    clear_tt();

    int best_move = open_c[0];
    int best_score = -30000;
    int completed_depth = 1;
    int proven = 0;

    int max_d = (max_depth > 0) ? max_depth : 12;
    if (R * C <= 30 && max_d < 16) max_d = 16; // 5x6 solve deep

    for (int d = 1; d <= max_d; d++) {
        int depth_best_move = open_c[0];
        int depth_best_score = -30000;
        int timeout_in_depth = 0;

        for (int i = 0; i < open_count; i++) {
            int c = open_c[i];
            uint128 np = (mask + g_bottom_bits[c]) & g_col_masks[c];
            uint128 above = np << 1;

            int val;
            if ((above & g_col_masks[c]) && check_win(opp_p | above, g_S, g_K)) {
                val = -(9000 + d);
            } else {
                val = -negamax(opp_p, mask | np, d - 1, -30000, 30000);
            }

            if (g_timeout_hit) {
                timeout_in_depth = 1;
                break;
            }

            if (val > depth_best_score) {
                depth_best_score = val;
                depth_best_move = c;
            }
        }

        if (timeout_in_depth) break;

        best_move = depth_best_move;
        best_score = depth_best_score;
        completed_depth = d;

        if (abs(best_score) >= 9000) {
            proven = 1;
            break; // Terminal win/loss found
        }
    }

    if (out_score) *out_score = best_score;
    if (out_depth) *out_depth = completed_depth;
    if (out_proven) *out_proven = proven;

    return one_indexed ? (best_move + 1) : best_move;
}
