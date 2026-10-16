/* halftone-core.h — 絲網印刷半調網點演算法核心
 *
 * 純 C 實作，不依賴 GIMP / GEGL，可在獨立測試程式中直接驗證。
 * 設計要點：
 *   - 藍雜訊（blue noise）門檻場取代規則網格 → 顆粒位置自然隨機
 *   - 隨機網 / 有序網佔比可調 → 兩種質感連續過渡
 *   - 網點邊界以角度諧波擾動 → 有機不規則形狀
 *   - 依門檻場梯度做解析式抗鋸齒 → 真實灰階網點邊緣
 *   - 密度校準（二分搜尋偏移量）→ 平均上墨率精確等於目標
 */
#ifndef HALFTONE_CORE_H
#define HALFTONE_CORE_H

#include <glib.h>
#include <math.h>
#include <string.h>

/* film-halftone.c — 絲網印刷用隨機顆粒半調網點外掛
 *
 * 目標：產生像膠片顆粒般自然隨機分佈、但仍可參數化控制的 halftone 網點。
 *
 * 設計要點
 *   - 藍雜訊（blue noise）門檻場取代傳統規則網格 → 顆粒位置自然隨機
 *   - 隨機網 / 有序網佔比可調 → 兩種質感之間連續過渡
 *   - 網點邊界以角度諧波擾動 → 有機不規則形狀，而非死板幾何形
 *   - 依網點場梯度做解析式抗鋸齒 → 真實灰階網點邊緣
 *   - 內建網點擴大補償與最小/最大網點夾限 → 對應網版印刷實務
 *
 * 本外掛走 GIMP 3 標準路徑：GimpPlugIn + GimpImageProcedure。
 * 像素運算自行以 gegl_buffer_iterator 讀寫圖層 buffer，不依賴 GIMP 核心
 * 內部的 GimpOperation / GimpDrawableFilterConfig（第三方無法存取）。
 *
 * UI 一律使用正體中文，不走 gettext，以確保任何語言設定下都顯示中文。
 */

#include <glib.h>
#include <math.h>
#include <string.h>

#define PLUG_IN_PROC "gimp-film-halftone"

#ifndef GIMP_PLUGIN_MIN_VERSION
#  define GIMP_PLUGIN_MIN_VERSION "3.0"
#endif

/* 網點形狀 */
enum
{
  DOT_SHAPE_ROUND,
  DOT_SHAPE_SQUARE,
  DOT_SHAPE_ELLIPSE,
  NUM_DOT_SHAPES
};

/* 輸出模式 */
enum
{
  OUT_GRAYSCALE,   /* 灰階網點（預覽用） */
  OUT_BINARY,      /* 二值（實際製版）    */
  OUT_INVERTED,    /* 反相                */
  NUM_OUTPUT_MODES
};

/* ==========================================================================
 * 參數結構
 * ======================================================================== */

typedef struct
{
  gdouble  frequency;     /* 網點頻率 lpi                          */
  gdouble  resolution;    /* 輸入解析度 dpi                        */
  gint     dot_shape;     /* 網點形狀                              */
  gdouble  shape_amount;  /* 網點不規則度 0..1                     */
  gdouble  stochastic;    /* 隨機網佔比 0..1                       */
  gdouble  grain_scale;   /* 顆粒粗細（網點間距的倍率）            */
  gint     noise_size;    /* 藍雜訊尺寸                            */
  gdouble  angle;         /* 網屏角度（度）                        */
  gdouble  dot_gain;      /* 網點擴大補償 0..1                      */
  gdouble  min_dot;       /* 最小網點 0..1                         */
  gdouble  max_dot;       /* ���大網點 0..1                         */
  gint     output_mode;   /* 輸出模式                              */
  gboolean antialias;     /* 邊緣抗鋸齒                            */
  gint     seed;          /* 隨機種子                              */
} FilmHalftoneParams;

/* ==========================================================================
 * 數學工具
 * ======================================================================== */

static inline gdouble
clamp01 (gdouble v)
{
  if (v < 0.0) return 0.0;
  if (v > 1.0) return 1.0;
  return v;
}

static inline gdouble
smoothstep (gdouble edge0, gdouble edge1, gdouble x)
{
  gdouble t = clamp01 ((x - edge0) / (edge1 - edge0));

  return t * t * (3.0 - 2.0 * t);
}

static inline gint
wrap_index (gint i, gint n)
{
  i %= n;

  return (i < 0) ? i + n : i;
}

/* 決定性整數雜湊：同一 seed 必得同一結果，方便微調單一參數後重現 */
static inline guint32
hash_u32 (guint32 x, guint32 seed)
{
  x ^= seed * 0x9e3779b9u + 0x85ebca6bu;
  x ^= x >> 16;
  x *= 0x7feb352du;
  x ^= x >> 15;
  x *= 0x846ca68bu;
  x ^= x >> 16;

  return x;
}

static inline gdouble
hash_unit (gint x, gint y, guint32 seed)
{
  guint32 h = hash_u32 ((guint32) x * 73856093u ^
                        (guint32) y * 19349663u, seed);

  return (gdouble) (h >> 8) / 16777216.0;
}


/* ==========================================================================
 * 藍雜訊生成器 — Void-and-Cluster 演算法
 *
 * Ulichney 1993。藍雜訊能量集中在高頻、低頻平坦，視覺上融合為平滑中間調，
 * 而非像白雜訊那樣「吵」。這正是膠片顆粒的統計特性。
 *
 * 實作關鍵：全程只需「距離場單調新增來源」
 *   稀疏階段移除網點 → 背景增加（距離來源增加），距離場只會變小；
 *   填補階段加入網點 → 前景增加，同理。
 * 因此兩階段都能用簡單 BFS 鬆弛，不必做昂貴的完整距離變換。
 * 每步 O(N²)，共 O(N²) 步；N=64 僅需數十毫秒。
 *
 * 環狀邊界 → 圖樣可無縫平鋪。
 * ======================================================================== */

#define BN_MAX_SIZE 256

typedef struct
{
  gint     size;    /* 邊長 N，場大小 N×N */
  gfloat  *field;   /* N*N，值域 0..1     */
} BlueNoise;

/* 由已初始化的來源做 BFS 鬆弛，更新 distance[]（單位為 4-鄰接步數）。
 * queue 既是初始來源清單，也作為 BFS 佇列；容量須足夠容納整張圖。 */
static void
bn_bfs_relax (gint *dist,
              gint  n,
              gint *queue,
              gint  nq)
{
  gint head = 0;

  while (head < nq)
    {
      gint idx = queue[head++];
      gint cx  = idx % n;
      gint cy  = idx / n;
      gint d   = dist[idx];
      gint k;

      for (k = 0; k < 4; k++)
        {
          static const gint ox[4] = {  1, -1,  0,  0 };
          static const gint oy[4] = {  0,  0,  1, -1 };
          gint nx = wrap_index (cx + ox[k], n);
          gint ny = wrap_index (cy + oy[k], n);
          gint ni = ny * n + nx;

          if (dist[ni] > d + 1)
            {
              dist[ni] = d + 1;
              queue[nq++] = ni;
            }
        }
    }
}

/* 產生藍雜訊門檻場，成功回傳 TRUE */
static gboolean
blue_noise_generate (BlueNoise *bn,
                     gint       size,
                     gint       seed)
{
  gint     total;
  guint8  *binary;
  gint    *dist;
  gint    *queue;
  gint    *ranking;
  guint32  s = (guint32) seed * 2654435761u + 12345u;
  gint     n_dots;
  gint     i;
  gint     k;

  if (size < 16)
    size = 16;
  if (size > BN_MAX_SIZE)
    size = BN_MAX_SIZE;

  total = size * size;

  binary  = g_new0 (guint8, total);
  dist    = g_new  (gint, total);
  /* BFS 不做 visited 標記，同一像素最多因 4 個鄰居而被重新入列，
   * 故佇列容量須為 total 的數倍，否則會越界。 */
  queue   = g_new  (gint, total * 4 + 16);
  ranking = g_new  (gint, total);

  /* --- 初始稀疏布點（約 10% 密度） --- */
  n_dots = 0;
  for (i = 0; i < total; i++)
    {
      if (hash_unit (i, 7, s) < 0.10)
        {
          binary[i] = 1;
          n_dots++;
        }
    }

  if (n_dots == 0)
    {
      binary[0] = 1;
      n_dots    = 1;
    }

  /* ================ 階段一：Void（移除最孤立的網點） ================ */
  {
    /* 收到初始密度的一半：如此「移除數 + 加入數」恰好等於 total，
     * ranking 陣列不會溢出（否則會堆積破壞）。 */
    gint target = n_dots / 2;

    if (target < 1)
      target = 1;

    /* dist[i] = 到最近「背景(0)」的距離 */
    {
      gint nq = 0;

      for (i = 0; i < total; i++)
        {
          if (binary[i] == 0)
            {
              dist[i] = 0;
              queue[nq++] = i;
            }
          else
            {
              dist[i] = G_MAXINT;
            }
        }

      bn_bfs_relax (dist, size, queue, nq);
    }

    k = 0;
    while (n_dots > target)
      {
        gint    best = -1;
        gint    iter_no = k;
        gint    nq;
        gdouble best_score = -1.0;

        /* 以「距離 + 隨機微擾」挑選：若永遠取第一個最大值，
         * 反覆執行會在固定方向累積成條帶狀偽影，隨機化可有效消除。 */
        for (i = 0; i < total; i++)
          if (binary[i] == 1)
            {
              gdouble score = (gdouble) dist[i] +
                              0.999 * hash_unit (i, iter_no, s);

              if (score > best_score)
                {
                  best_score = score;
                  best       = i;
                }
            }

        if (best < 0)
          break;

        binary[best] = 0;      /* 移除此孤立網點 */
        n_dots--;
        if (k < total)
          ranking[k++] = best;   /* 由「最孤立」開始記錄 */

        /* 背景新增一個來源 → 距離場鬆弛 */
        dist[best] = 0;
        nq = 0;
        queue[nq++] = best;
        bn_bfs_relax (dist, size, queue, nq);
      }
  }

  /* ================ 階段二：Cluster（填補最擁擠的點） ================ */
  {
    gint nq = 0;

    /* dist[i] = 到最近「網點(1)」的距離 */
    for (i = 0; i < total; i++)
      {
        if (binary[i] == 1)
          {
            dist[i] = 0;
            queue[nq++] = i;
          }
        else
          {
            dist[i] = G_MAXINT;
          }
      }

    bn_bfs_relax (dist, size, queue, nq);

    while (n_dots < total)
      {
        gint    best = -1;
        gint    iter_no = k;
        gdouble best_score = -1.0;

        /* 同樣隨機化打破並列，避免方向性條帶 */
        for (i = 0; i < total; i++)
          if (binary[i] == 0 && dist[i] < G_MAXINT)
            {
              gdouble score = (gdouble) dist[i] +
                              0.999 * hash_unit (i, iter_no + 7919, s);

              if (score > best_score)
                {
                  best_score = score;
                  best       = i;
                }
            }

        if (best < 0)
          break;

        binary[best] = 1;      /* 在最空曠處補上網點 */
        n_dots++;
        if (k < total)
          ranking[k++] = best;   /* 由「最擁擠」繼續記錄 */

        /* 前景新增一個來源 → 距離場鬆弛 */
        dist[best] = 0;
        nq = 0;
        queue[nq++] = best;
        bn_bfs_relax (dist, size, queue, nq);
      }
  }

  /* --- 依 ranking 產生 0..1 的門檻場 --- */
  bn->size  = size;
  bn->field = g_new (gfloat, total);

  for (i = 0; i < total; i++)
    bn->field[i] = 0.5f;   /* 未被記錄到的像素給中間值 */

  for (i = 0; i < k && i < total; i++)
    bn->field[ranking[i]] = (gfloat) i / (gfloat) (total - 1);

  g_free (binary);
  g_free (dist);
  g_free (queue);
  g_free (ranking);

  return TRUE;
}

/* 雙線性取樣（環狀邊界 → 無縫平鋪） */
static inline gdouble
blue_noise_sample (const BlueNoise *bn,
                   gdouble          x,
                   gdouble          y)
{
  gint     n  = bn->size;
  gdouble  fx = x - floor (x / n) * n;
  gdouble  fy = y - floor (y / n) * n;
  gint     ix = (gint) fx;
  gint     iy = (gint) fy;
  gdouble  tx = fx - ix;
  gdouble  ty = fy - iy;
  gint     x0 = wrap_index (ix, n);
  gint     y0 = wrap_index (iy, n);
  gint     x1 = wrap_index (ix + 1, n);
  gint     y1 = wrap_index (iy + 1, n);
  gfloat  *f  = bn->field;
  gdouble  v00 = f[y0 * n + x0];
  gdouble  v10 = f[y0 * n + x1];
  gdouble  v01 = f[y1 * n + x0];
  gdouble  v11 = f[y1 * n + x1];
  gdouble  a   = v00 * (1.0 - tx) + v10 * tx;
  gdouble  b   = v01 * (1.0 - tx) + v11 * tx;

  return a * (1.0 - ty) + b * ty;
}


/* ==========================================================================
 * 網點場
 *
 * 關鍵性質：AM 門檻場以「距離平方」構造，保證網點面積精確等於灰階值，
 * 因此不會整體偏亮或偏暗。兩種距離度量皆滿足此性質：
 *   圓形/橢圓 → 面積 = πr²，故 threshold = π (r/cell)²
 *   方形      → 面積 = 4r²，故 threshold = (2r/cell)²
 * ======================================================================== */

typedef struct
{
  gdouble cell;          /* 網點間距（像素）      */
  gdouble inv_cell;
  gdouble cos_a, sin_a;  /* 網屏旋轉              */
  gdouble radius;        /* 網點基準半徑 = cell/2 */
  gdouble shape_amount;
  gdouble harm_a[3];     /* 形狀擾動諧波係數     */
  gdouble harm_b[3];     /* 形狀擾動相位          */
  gint    shape;
  gdouble bn_span;       /* 藍雜訊取樣跨度        */
  gdouble stochastic;    /* 隨機網佔比            */
} DotField;

/* 由參數建立網點場 */
static void
dot_field_init (DotField             *f,
                const BlueNoise      *bn,
                const FilmHalftoneParams *p)
{
  gint    i;
  gdouble cell;
  gdouble grain_px;

  cell = p->resolution / p->frequency;
  if (cell < 2.0)   cell = 2.0;
  if (cell > 512.0) cell = 512.0;

  f->cell         = cell;
  f->inv_cell     = 1.0 / cell;
  f->radius       = cell * 0.5;
  f->shape_amount = p->shape_amount;
  f->shape        = p->dot_shape;
  f->stochastic   = p->stochastic;

  {
    gdouble rad = p->angle * G_PI / 180.0;

    f->cos_a = cos (rad);
    f->sin_a = sin (rad);
  }

  /* 形狀擾動：三個低階諧波，由種子決定性產生 */
  for (i = 0; i < 3; i++)
    {
      f->harm_a[i] = (hash_unit (i, 11, p->seed) - 0.5) * 2.0;
      f->harm_b[i] = hash_unit (i, 23, p->seed) * 2.0 * G_PI;
    }

  /* 藍雜訊取樣跨度：使相關長度 ≈ grain_px
   * 藍雜訊特徵約為 tile 的 1/8，故一個 tile 覆蓋 8×grain_px 像素。 */
  grain_px = cell * p->grain_scale;
  if (grain_px < 1.0)
    grain_px = 1.0;

  f->bn_span = (gdouble) bn->size / (8.0 * grain_px);
}

/* 計算單一點的門檻場值 T（越大越不容易上墨） */
static inline gdouble
dot_field_threshold (const DotField *f,
                     const BlueNoise *bn,
                     gint       x,
                     gint       y)
{
  gdouble  dx, dy, d;
  gdouble  T_am, T_stoch;

  /* --- 旋轉到網屏座標系，取最近網格中心的相對位置 --- */
  {
    gdouble rx  = x * f->cos_a - y * f->sin_a;
    gdouble ry  = x * f->sin_a + y * f->cos_a;
    gdouble cx  = fmod (rx + f->radius, f->cell);
    gdouble cy  = fmod (ry + f->radius, f->cell);

    dx = cx - f->radius;
    dy = cy - f->radius;
  }

  /* --- 形狀擾動：讓邊界半徑隨角度自然起伏 --- */
  if (f->shape_amount > 0.0 && (dx * dx + dy * dy) > 0.0)
    {
      gdouble ang  = atan2 (dy, dx);
      gdouble mod1 = 0.0;

      mod1 += f->harm_a[0] * cos (2.0 * ang + f->harm_b[0]);
      mod1 += f->harm_a[1] * cos (3.0 * ang + f->harm_b[1]);
      mod1 += f->harm_a[2] * cos (5.0 * ang + f->harm_b[2]);

      d = sqrt (dx * dx + dy * dy) * (1.0 + f->shape_amount * mod1);
    }
  else
    {
      d = sqrt (dx * dx + dy * dy);
    }

  /* --- 由距離推出門檻，使網點面積精確等於灰階值 --- */
  if (f->shape == DOT_SHAPE_SQUARE)
    {
      gdouble q = fmax (fabs (dx), fabs (dy));

      T_am = 4.0 * q * q * f->inv_cell * f->inv_cell;
    }
  else if (f->shape == DOT_SHAPE_ELLIPSE)
    {
      /* 1.35 : 1 長軸圓，兼顧網版印刷穩定性與有機感 */
      const gdouble k = 1.35;
      gdouble u = (dx / k) * f->inv_cell;
      gdouble v = (dy * k) * f->inv_cell;

      T_am = G_PI * (u * u + v * v);
    }
  else /* DOT_SHAPE_ROUND */
    {
      gdouble u = d * f->inv_cell;

      T_am = G_PI * u * u;
    }

  /* --- 隨機網場 --- */
  if (bn && f->stochastic > 0.0)
    T_stoch = blue_noise_sample (bn, x * f->bn_span, y * f->bn_span);
  else
    T_stoch = 0.5;

  /* --- 依佔比混合：0 = 純隨機（膠片感），1 = 純有序網格 --- */
  return T_stoch * f->stochastic + T_am * (1.0 - f->stochastic);
}

/* 網點擴大補償：印刷時油墨擴張使實際網點變大，故預先縮小。
 * 模型 t/(1 + gain·4t(1-t))，中間調影響最大，符合暗部擴張最嚴重的實況。 */
static inline gdouble
dot_gain_compensate (gdouble t,
                     gdouble gain)
{
  if (gain <= 0.0)
    return t;

  return t / (1.0 + gain * 4.0 * t * (1.0 - t));
}


/* ==========================================================================
 * 密度校準
 *
 * 隨機網與有序網混合時，單純門檻比較未必讓平均上墨率等於目標密度。
 * 因此先累積 (tone - T) 的分佈直方圖，再二分搜尋一個全域偏移量 bias，
 * 使平均上墨率精確等於目標密度 —— 這對印刷的階調還原是必要的。
 * 記憶體用量固定為 512 個 bin，與影像尺寸無關。
 * ======================================================================== */

#define DENSITY_BINS 512
#define DENSITY_LO (-1.6)
#define DENSITY_HI  ( 1.0)

typedef struct
{
  const FilmHalftoneParams *params;
  DotField                  field;
  BlueNoise                 noise;
  gdouble                   hist[DENSITY_BINS];
  gdouble                   hist_total;
  gdouble                   target_density;
} HalftoneContext;

/* 累積一個像素的差值到直方圖 */
static inline void
halftone_accumulate (HalftoneContext *ctx,
                     gdouble          tone,
                     gdouble          thresh)
{
  gdouble d = tone - thresh;
  gdouble f = (d - DENSITY_LO) / (DENSITY_HI - DENSITY_LO);
  gint    b = (gint) (f * (DENSITY_BINS - 1) + 0.5);

  if (b < 0)                 b = 0;
  if (b >= DENSITY_BINS)     b = DENSITY_BINS - 1;

  ctx->hist[b]     += 1.0;
  ctx->hist_total  += 1.0;
  ctx->target_density += tone;
}

/* 求解偏移量 bias，使平均上墨率等於目標密度（兩分搜尋，單調遞減） */
static gdouble
halftone_solve_density_bias (HalftoneContext *ctx)
{
  gdouble lo = DENSITY_LO;
  gdouble hi = DENSITY_HI;
  gdouble target;
  gint    iter;

  if (ctx->hist_total <= 0.0)
    return 0.0;

  target = ctx->target_density / ctx->hist_total;

  for (iter = 0; iter < 48; iter++)
    {
      gdouble mid = 0.5 * (lo + hi);
      gdouble f   = (mid - DENSITY_LO) / (DENSITY_HI - DENSITY_LO);
      gint    idx = (gint) (f * (DENSITY_BINS - 1) + 0.5);
      gdouble ink = 0.0;
      gint    b;

      if (idx < 0)             idx = 0;
      if (idx >= DENSITY_BINS) idx = DENSITY_BINS - 1;

      /* d > bias → 上墨 */
      for (b = idx; b < DENSITY_BINS; b++)
        ink += ctx->hist[b];

      ink /= ctx->hist_total;

      if (ink > target)
        lo = mid;      /* 上墨過多 → 提高門檻 */
      else
        hi = mid;
    }

  return 0.5 * (lo + hi);
}

/* 對單一像素套用網點，回傳上墨覆蓋率 0..1 */
static inline gdouble
halftone_pixel (HalftoneContext *ctx,
                gint             x,
                gint             y,
                gdouble          tone,
                gdouble          bias)
{
  const FilmHalftoneParams *p = ctx->params;
  gdouble t, T;
  const gdouble soft = 0.5;   /* 過渡半寬（像素） */

  /* 網點擴大補償 → 夾限到最小/最大網點 */
  t = clamp01 (dot_gain_compensate (tone, p->dot_gain));
  if (t < p->min_dot) t = p->min_dot;
  if (t > p->max_dot) t = p->max_dot;

  T = dot_field_threshold (&ctx->field, &ctx->noise, x, y) + bias;

  if (! p->antialias)
    return (t >= T) ? 1.0 : 0.0;

  /* 解析式抗鋸齒：以門檻場梯度換算「到網點邊界的像素距離」 */
  {
    gdouble Tx1 = dot_field_threshold (&ctx->field, &ctx->noise, x + 1, y) + bias;
    gdouble Tx0 = dot_field_threshold (&ctx->field, &ctx->noise, x - 1, y) + bias;
    gdouble Ty1 = dot_field_threshold (&ctx->field, &ctx->noise, x, y + 1) + bias;
    gdouble Ty0 = dot_field_threshold (&ctx->field, &ctx->noise, x, y - 1) + bias;
    gdouble gx  = (Tx1 - Tx0) * 0.5;
    gdouble gy  = (Ty1 - Ty0) * 0.5;
    gdouble g2  = gx * gx + gy * gy;
    gdouble d;

    if (g2 < 1e-12)
      return (t >= T) ? 1.0 : 0.0;

    d = (t - T) / sqrt (g2);   /* 為正表示落在網點內側 */

    return smoothstep (-soft, soft, d);
  }
}

/* 依輸出模式轉換最終灰階值
 *
 * 極性以「黑墨白底」為準（網版印刷的實際輸出）：
 *   上墨覆蓋率 ink = 0 表示無墨 → 紙面呈白 (1.0)
 *                     ink = 1 表示滿墨 → 紙面呈黑 (0.0)
 * 故灰階輸出為 1 - ink；反相模式則為白墨黑底 (正片)，即 ink。
 */
static inline gdouble
halftone_apply_output (gint    mode,
                       gdouble ink)
{
  switch (mode)
    {
    case OUT_BINARY:
      return (ink > 0.5) ? 0.0 : 1.0;   /* 黑墨白底二值 */

    case OUT_INVERTED:
      return ink;                       /* 白墨黑底（正片遮罩） */

    case OUT_GRAYSCALE:
    default:
      return 1.0 - ink;                 /* 黑墨白底灰階 */
    }
}

/* ==========================================================================
 * 整張影像渲染
 *
 * src: w*h 的灰度值，0 = 全黑（全墨），1 = 全白
 * dst: w*h 的紙面明度，黑墨白底故 0 = 滿墨（黑）、1 = 無墨（白）
 *
 * 回傳 FALSE 代表失敗且 dst 未被寫入，呼叫端必須自行處理；
 * 不可在使用失敗結果的情況下把未初始化的記憶體寫回圖層。
 * ======================================================================== */

gboolean
film_halftone_render (const FilmHalftoneParams *params,
                      gint        w,
                      gint        h,
                      const gfloat *src,
                      gfloat     *dst)
{
  HalftoneContext ctx;
  FilmHalftoneParams  p_store = *params;
  const FilmHalftoneParams *p = &p_store;
  gdouble        bias;
  gint           x, y;

  g_return_val_if_fail (params != NULL, FALSE);
  g_return_val_if_fail (src   != NULL, FALSE);
  g_return_val_if_fail (dst   != NULL, FALSE);
  g_return_val_if_fail (w > 0 && h > 0, FALSE);

  /* 二值輸出本來就是硬門檻，若仍先做抗鋸齒再二值化，
   * 會二次量化而使墨量偏移，故直接關閉抗鋸齒。 */
  if (p->output_mode == OUT_BINARY)
    p_store.antialias = FALSE;

  memset (&ctx, 0, sizeof (ctx));
  ctx.params = p;

  if (! blue_noise_generate (&ctx.noise, p->noise_size, p->seed))
    return FALSE;

  dot_field_init (&ctx.field, &ctx.noise, p);

  /* 第一趟：累積 (tone - T) 直方圖，求全域密度校準偏移 */
  for (y = 0; y < h; y++)
    for (x = 0; x < w; x++)
      {
        gint    i  = y * w + x;
        gdouble t  = clamp01 (dot_gain_compensate (src[i], p->dot_gain));
        gdouble T;

        if (t < p->min_dot) t = p->min_dot;
        if (t > p->max_dot) t = p->max_dot;

        T = dot_field_threshold (&ctx.field, &ctx.noise, x, y);

        halftone_accumulate (&ctx, t, T);
      }

  bias = halftone_solve_density_bias (&ctx);

  /* 第二趟起：迭代校準。
   * 抗鋸齒會把網點邊緣平滑成灰階過渡，實際墨量會低於二值判定所預測的值，
   * 因此先算一次墨量，再用實測誤差修正偏移量。
   * 因門檻場 T 在 0..1 上近似均勻分佈，故 d(墨量)/d(bias) ≈ -1，
   * 一次修正即可把誤差壓到 0.5% 以內。
   */
  {
    gdouble mean_tone  = ctx.target_density / ctx.hist_total;
    gdouble target_ink = 1.0 - mean_tone;   /* 墨量 = 1 - 平均灰階 */
    gint    iter;

    for (iter = 0; iter < 3; iter++)
      {
        gdouble mean_ink = 0.0;
        gdouble err;

        for (y = 0; y < h; y++)
          for (x = 0; x < w; x++)
            mean_ink += halftone_pixel (&ctx, x, y, src[y * w + x], bias);

        mean_ink /= (gdouble) (w * h);
        err = target_ink - mean_ink;

        if (err > -0.002 && err < 0.002)
          break;

        /* 提高門檻會減少墨量，故方向為減 */
        bias -= err;

        if (bias < -0.5) bias = -0.5;
        if (bias >  0.5) bias =  0.5;
      }
  }

  /* 最終輸出 */
  for (y = 0; y < h; y++)
    for (x = 0; x < w; x++)
      {
        gint    i   = y * w + x;
        gdouble ink = halftone_pixel (&ctx, x, y, src[i], bias);

        dst[i] = (gfloat) clamp01 (halftone_apply_output (p->output_mode, ink));
      }

  g_free (ctx.noise.field);

  return TRUE;
}

#endif /* HALFTONE_CORE_H */
