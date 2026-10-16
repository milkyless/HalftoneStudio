/* standalone.c — 絲網印刷半調網點演算法的獨立驗證程式
 *
 * 不依賴 GIMP，直接呼叫 halftone-core.h，輸出 PGM 影像與密度統計，
 * 用以快速驗證網點品質而無須反覆啟動 GIMP。
 */
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "halftone-core.h"

#define W 600
#define H 400

static void
write_pgm (const char *path, const gfloat *data, gint w, gint h)
{
  FILE *fp = fopen (path, "wb");
  gint  i;

  if (! fp)
    {
      fprintf (stderr, "無法開啟 %s\n", path);
      return;
    }

  fprintf (fp, "P5\n%d %d\n255\n", w, h);

  for (i = 0; i < w * h; i++)
    {
      gint v = (gint) (data[i] * 255.0f + 0.5f);

      if (v < 0)   v = 0;
      if (v > 255) v = 255;

      fputc (v, fp);
    }

  fclose (fp);
  printf ("  輸出 %s\n", path);
}

/* 產生橫向漸層：0（黑）→ 1（白） */
static void
make_gradient (gfloat *buf)
{
  gint x, y;

  for (y = 0; y < H; y++)
    for (x = 0; x < W; x++)
      buf[y * W + x] = (gfloat) x / (gfloat) (W - 1);
}

static void
run_case (const char           *tag,
          const FilmHalftoneParams *p)
{
  gfloat *src = g_malloc (sizeof (gfloat) * W * H);
  gfloat *dst = g_malloc (sizeof (gfloat) * W * H);
  char   path[256];
  clock_t t0;
  double  elapsed;
  double  want_ink, got_ink;
  gint    i;

  make_gradient (src);

  t0 = clock ();
  film_halftone_render (p, W, H, src, dst);
  elapsed = (double) (clock () - t0) / CLOCKS_PER_SEC;

  g_snprintf (path, sizeof (path), "core_%s.pgm", tag);
  write_pgm (path, dst, W, H);

  /* 期望上墨率須以「網點擴大補償 + 最小/最大網點夾限」後的灰階計算，
   * 否則會把設計上的預先縮小誤判為誤差。 */
  want_ink = 0.0;
  got_ink  = 0.0;
  for (i = 0; i < W * H; i++)
    {
      gdouble t = dot_gain_compensate ((gdouble) src[i], p->dot_gain);

      if (t < p->min_dot) t = p->min_dot;
      if (t > p->max_dot) t = p->max_dot;

      want_ink += 1.0 - t;

      /* dst 是「紙面明度」：黑墨白底下 0 = 滿墨、1 = 無墨。
       * 反相模式則相反。所有模式一律以 1 - dst 換算成上墨覆蓋率。 */
      got_ink  += 1.0 - dst[i];
    }
  want_ink /= (double) (W * H);
  got_ink  /= (double) (W * H);

  printf ("%-10s ink want %.4f got %.4f  err %+.4f  |  %.3f s\n",
          tag, want_ink, got_ink, got_ink - want_ink, elapsed);

  g_free (src);
  g_free (dst);
}

/* 匯出藍雜訊場本身，用於診斷 */
static void
dump_blue_noise (gint size, gint seed)
{
  BlueNoise bn;
  gfloat  *buf;
  char     path[256];
  gint     x, y;

  if (! blue_noise_generate (&bn, size, seed))
    return;

  buf = g_malloc (sizeof (gfloat) * size * size);

  for (y = 0; y < size; y++)
    for (x = 0; x < size; x++)
      buf[y * size + x] = bn.field[y * size + x];

  g_snprintf (path, sizeof (path), "bluenoise_%d_seed%d.pgm", size, seed);
  write_pgm (path, buf, size, size);

  /* 統計局部均勻性：以 8x8 區塊計算密度變異係數，越小越均勻 */
  {
    gdouble sum = 0.0, sum2 = 0.0;
    gint    nblk = 0;

    for (y = 0; y + 8 <= size; y += 8)
      for (x = 0; x + 8 <= size; x += 8)
        {
          gdouble c = 0.0;
          gint    j, i;

          for (j = 0; j < 8; j++)
            for (i = 0; i < 8; i++)
              c += (buf[(y + j) * size + (x + i)] < 0.5) ? 1.0 : 0.0;

          c /= 64.0;
          sum  += c;
          sum2 += c * c;
          nblk++;
        }

    if (nblk)
      {
        gdouble mean = sum / nblk;
        gdouble var  = sum2 / nblk - mean * mean;

        printf ("  bluenoise %dx%d seed=%d : 8x8 區塊密度 %.4f, 標準差 %.4f\n",
                size, size, seed, mean, sqrt (var));
      }
  }

  g_free (buf);
  g_free (bn.field);
}

/* 以固定灰階渲染整張圖，用於隔離檢視網點結構 */
static void
run_flat (const char *tag, gdouble level, const FilmHalftoneParams *p)
{
  gfloat *src = g_malloc (sizeof (gfloat) * W * H);
  gfloat *dst = g_malloc (sizeof (gfloat) * W * H);
  char   path[256];
  gint   i;

  for (i = 0; i < W * H; i++)
    src[i] = (gfloat) level;

  film_halftone_render (p, W, H, src, dst);

  g_snprintf (path, sizeof (path), "flat_%s.pgm", tag);
  write_pgm (path, dst, W, H);

  g_free (src);
  g_free (dst);
}

int
main (void)
{
  FilmHalftoneParams p;
  gint              i;

  /* 預設參數 */
  p.frequency    = 40.0;
  p.resolution   = 300.0;
  p.dot_shape    = DOT_SHAPE_ROUND;
  p.shape_amount = 0.0;
  p.stochastic   = 0.0;
  p.grain_scale  = 1.0;
  p.noise_size   = 64;
  p.angle        = 15.0;
  p.dot_gain     = 0.15;
  p.min_dot      = 0.03;
  p.max_dot      = 0.95;
  p.output_mode  = OUT_GRAYSCALE;
  p.antialias    = TRUE;
  p.seed         = 0;

  printf ("=== 絲網印刷半調網點核心驗證 (%dx%d) ===\n", W, H);

  /* 1. 網點頻率的影響 */
  for (i = 0; i < 3; i++)
    {
      char tag[32];

      p.frequency = (i == 0) ? 20.0 : (i == 1) ? 40.0 : 85.0;
      g_snprintf (tag, sizeof (tag), "lpi%d", (int) p.frequency);
      run_case (tag, &p);
    }

  /* 2. 隨機網佔比（核心需求） */
  p.frequency = 40.0;
  for (i = 0; i <= 4; i++)
    {
      char tag[32];

      p.stochastic = i / 4.0;
      g_snprintf (tag, sizeof (tag), "mix%d", i * 25);
      run_case (tag, &p);
    }

  /* 3. 網點不規則度（有機顆粒感） */
  p.stochastic   = 0.2;
  p.shape_amount = 0.6;
  run_case ("organic", &p);

  /* 4. 二值輸出 */
  p.output_mode = OUT_BINARY;
  run_case ("binary", &p);

  /* 5. 可重現性：同種子結果應完全一致 */
  p.output_mode = OUT_GRAYSCALE;
  run_case ("seed_a", &p);
  p.seed = 1;
  run_case ("seed_b", &p);

  run_flat ("am50", 0.5, &p);

  p.stochastic = 0.5;
  run_flat ("mix50", 0.5, &p);

  p.stochastic = 1.0;
  run_flat ("st50", 0.5, &p);

  p.stochastic = 0.25;
  run_flat ("mix25f", 0.5, &p);

  p.stochastic   = 0.25;
  p.shape_amount = 0.6;
  run_flat ("organic", 0.5, &p);

  dump_blue_noise (64, 0);
  printf ("=== 驗證完成 ===\n");
  return 0;
}
