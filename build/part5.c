/* ==========================================================================
 * 圖層處理
 *
 * 網點演算法本身位於 halftone-core.h（純 C、不依賴 GEGL），
 * 此處只負責 GIMP 層的讀寫與灰度換算。
 *
 * 以 "R'G'B'A float" 迭代圖層 buffer：GEGL 會自動在影像原生格式與 float
 * 之間轉換，因此 8-bit 灰階、16-bit、32-bit 浮點圖層都能正確處理；
 * 寫回時同樣由 GEGL 轉回原生格式。
 *
 * 流程：讀取 → Rec.709 亮度 → 交給核心渲染器 → 寫回並保留原透明度
 * ======================================================================== */

#include <libgimp/gimp.h>
#include <gegl.h>
#include <glib/gstdio.h>   /* g_fopen / g_fprintf（暫時診斷日誌用） */

#include "halftone-core.h"

#define LUM_R 0.2126
#define LUM_G 0.7152
#define LUM_B 0.0722

/* R'G'B'A 為 RGBA 四通道 */
#define FH_CHANNELS 4

/* ==========================================================================
 * 【暫時診斷日誌】確認問題後請整段刪除
 *
 * 設環境變數 FH_LOG=1 才會啟用，正式使用時完全不佔額外資源。
 * ========================================================================== */

static FILE *
fh_log (void)
{
  static FILE *fp  = NULL;
  static gboolean tried = FALSE;

  if (! tried)
    {
      const gchar *env = g_getenv ("FH_LOG");

      tried = TRUE;

      if (env && *env && g_ascii_strtoll (env, NULL, 10) != 0)
        {
          gchar *path = g_build_filename (g_get_tmp_dir (),
                                          "film-halftone.log", NULL);

          fp = g_fopen (path, "w");
          if (fp)
            g_fprintf (fp, "=== film-halftone 診斷日誌 ===\n");

          g_free (path);
        }
    }

  return fp;
}

#define FH_LOG(...) G_STMT_START {                 \
    FILE *_fp = fh_log ();                         \
    if (_fp) {                                     \
      g_fprintf (_fp, __VA_ARGS__);                \
      g_fprintf (_fp, "\n");                       \
      fflush (_fp);                                \
    }                                              \
  } G_STMT_END

#define FH_LOG_PIXELS(tag, arr, count) G_STMT_START {          \
    FILE *_fp = fh_log ();                                      \
    if (_fp) {                                                  \
      gint _i, _lim = MIN ((gint) (count), 5);                  \
      g_fprintf (_fp, "%s 前 5 點: ", tag);                     \
      for (_i = 0; _i < _lim; _i++)                             \
        g_fprintf (_fp, "%.4f ", (double) (arr)[_i]);           \
      g_fprintf (_fp, "\n");                                    \
      fflush (_fp);                                             \
    }                                                           \
  } G_STMT_END

static gboolean
halftone_process_buffer (const FilmHalftoneParams *params,
                         GeglBuffer             *buffer,
                         gint                    width,
                         gint                    height)
{
  const Babl   *format = babl_format ("R'G'B'A float");
  GeglRectangle roi;
  gfloat       *src;
  gfloat       *dst;
  gint          n;
  gboolean      ok;

  roi.x = 0;
  roi.y = 0;
  roi.width  = width;
  roi.height = height;

  n   = width * height;
  src = g_new (gfloat, n);
  dst = g_new (gfloat, n);

  FH_LOG ("[進入] halftone_process_buffer 尺寸 %dx%d 像素數 %d",
          width, height, n);
  FH_LOG ("[參數] freq=%.1f res=%.1f shape=%d amount=%.2f "
          "stoch=%.2f grain=%.2f noise=%d angle=%.1f "
          "gain=%.2f min=%.2f max=%.2f out=%d aa=%d seed=%d",
          params->frequency, params->resolution, params->dot_shape,
          params->shape_amount, params->stochastic, params->grain_scale,
          params->noise_size, params->angle, params->dot_gain,
          params->min_dot, params->max_dot, params->output_mode,
          params->antialias ? 1 : 0, params->seed);
  FH_LOG ("[格式] babl R'G'B'A float = %p", (gpointer) format);
  FH_LOG ("[進度] 正在讀取影像…");

  gimp_progress_init ("正在讀取影像…");

  /* --- 讀取並轉灰階 --- */
  {
    GeglBufferIterator *iter;
    gboolean            cancel = FALSE;
    gint                chunks = 0;

    iter = gegl_buffer_iterator_new (buffer, &roi, 0, format,
                                     GEGL_BUFFER_READ,
                                     GEGL_ABYSS_CLAMP, 1);

    FH_LOG ("[讀取] iterator 建立結果 = %p", (gpointer) iter);

    if (! iter)
      {
        FH_LOG ("[致命] 讀取 iterator 建立失敗，直接中止");
        g_free (src);
        g_free (dst);
        return FALSE;
      }

    while (gegl_buffer_iterator_next (iter))
      {
        gfloat     *px = (gfloat *) iter->items[0].data;
        gint        x0 = iter->items[0].roi.x;
        gint        y0 = iter->items[0].roi.y;
        gint        w  = iter->items[0].roi.width;
        gint        h  = iter->items[0].roi.height;
        gint        j, i;

        /* 關鍵：iter->length 是整塊的「像素」數，不是位元組數，
         * 且不保證等於 w*h（GEGL 會依實際可用緩衝切分）。
         * 因此每列的 float 數量為：
         *     每列像素數 = length / h
         *     每列 float 數 = 每列像素數 × 通道數
         * 早期版本誤把 length 當位元組數，導致越界崩潰。 */
        gsize stride = (h > 0)
                     ? (gsize) (iter->length / h) * FH_CHANNELS
                     : 0;

        if (chunks == 0)
          FH_LOG ("[讀取] 第一塊 roi=(%d,%d) %dx%d length=%d(像素) "
                  "每列=%u float 應為 %d",
                  x0, y0, w, h, iter->length,
                  (guint) stride, w * FH_CHANNELS);

        if (stride < (gsize) w * 4)
          {
            FH_LOG ("[致命] 行距 %u 小於每列 %d，資料格式不符",
                    (guint) stride, w * 4);
            cancel = TRUE;
            break;
          }

        for (j = 0; j < h; j++)
          {
            gfloat *p = px + (gsize) j * stride;

            for (i = 0; i < w; i++)
              {
                gint idx = (y0 + j) * width + (x0 + i);

                src[idx] = (gfloat) clamp01 (LUM_R * p[i * 4 + 0] +
                                             LUM_G * p[i * 4 + 1] +
                                             LUM_B * p[i * 4 + 2]);
              }
          }

        chunks++;

        gegl_buffer_iterator_stop (iter);

        if (! gimp_progress_update (20.0))
          {
            cancel = TRUE;
            break;
          }
      }

    g_object_unref (iter);

    FH_LOG ("[讀取] 完成，共 %d 塊，cancel=%d", chunks, cancel ? 1 : 0);
    FH_LOG_PIXELS ("[讀取] 灰階 src", src, n);

    if (cancel)
      {
        g_free (src);
        g_free (dst);
        return FALSE;
      }
  }

  gimp_progress_end ();

  FH_LOG ("[進度] 讀取階段結束");

  /* --- 產生網點 ---
   *
   * render() 失敗時 dst 未被寫入，此時必須放棄整次處理，
   * 絕不可把未初始化的記憶體寫回圖層。
   */
  if (! gimp_progress_init ("正在產生半調網點…"))
    {
      FH_LOG ("[致命] 進度條初始化失敗，無法顯示進度");
      g_free (src);
      g_free (dst);
      return FALSE;
    }

  FH_LOG ("[進度] 正在產生半調網點… 開始呼叫 render()");
  ok = film_halftone_render (params, width, height, src, dst);
  FH_LOG ("[render] 回傳 %s", ok ? "TRUE" : "FALSE");
  FH_LOG_PIXELS ("[render] 輸出 dst", dst, n);

  gimp_progress_end ();

  if (! ok)
    {
      FH_LOG ("[致命] render() 失敗，dst 未被寫入，放棄整次處理");
      g_free (src);
      g_free (dst);
      return FALSE;
    }

  /* --- 寫回 ---
   *
   * 採「先算出全部結果、確認無誤，再一次寫回」的策略：
   * 若中途被取消，就整段跳過寫回，避免圖層只被改了一半。
   */
  {
    GeglBufferIterator *read_iter;
    GeglBufferIterator *write_iter;
    gfloat             *alpha;
    gboolean            cancel = FALSE;
    gint                written = 0;

    alpha = g_new (gfloat, n);

    /* ① 讀回原始透明度 */
    read_iter = gegl_buffer_iterator_new (buffer, &roi, 0, format,
                                          GEGL_BUFFER_READ,
                                          GEGL_ABYSS_CLAMP, 1);

    FH_LOG ("[寫回] alpha 讀取 iterator = %p", (gpointer) read_iter);

    if (! read_iter)
      {
        FH_LOG ("[致命] alpha 讀取 iterator 建立失敗");
        g_free (alpha);
        g_free (src);
        g_free (dst);
        return FALSE;
      }

    while (gegl_buffer_iterator_next (read_iter))
      {
        const gfloat *px = (const gfloat *) read_iter->items[0].data;
        gint    x0 = read_iter->items[0].roi.x;
        gint    y0 = read_iter->items[0].roi.y;
        gint    w  = read_iter->items[0].roi.width;
        gint    h  = read_iter->items[0].roi.height;
        gint    j, i;
        gsize   stride = (h > 0)
                        ? (gsize) (read_iter->length / h) * FH_CHANNELS
                        : 0;

        if (stride < (gsize) w * FH_CHANNELS)
          {
            FH_LOG ("[致命] alpha 讀取行距不足");
            g_object_unref (read_iter);
            g_free (alpha);
            g_free (src);
            g_free (dst);
            return FALSE;
          }

        for (j = 0; j < h; j++)
          {
            const gfloat *p = px + (gsize) j * stride;

            for (i = 0; i < w; i++)
              alpha[(y0 + j) * width + (x0 + i)] = p[i * 4 + 3];
          }
      }

    gegl_buffer_iterator_stop (read_iter);
    g_object_unref (read_iter);

    FH_LOG_PIXELS ("[寫回] alpha", alpha, n);

    /* ② 寫入新的灰階值 */
    gimp_progress_init ("正在寫回圖層…");

    write_iter = gegl_buffer_iterator_new (buffer, &roi, 0, format,
                                           GEGL_BUFFER_WRITE,
                                           GEGL_ABYSS_CLAMP, 1);

    FH_LOG ("[寫回] WRITE iterator = %p", (gpointer) write_iter);

    if (! write_iter)
      {
        FH_LOG ("[致命] 寫入 iterator 建立失敗（格式不支援？緩衝區唯讀？）");
        gimp_progress_end ();
        g_free (alpha);
        g_free (src);
        g_free (dst);
        return FALSE;
      }

    while (gegl_buffer_iterator_next (write_iter))
      {
        gfloat *px = (gfloat *) write_iter->items[0].data;
        gint    x0 = write_iter->items[0].roi.x;
        gint    y0 = write_iter->items[0].roi.y;
        gint    w  = write_iter->items[0].roi.width;
        gint    h  = write_iter->items[0].roi.height;
        gint    j, i;
        gsize   stride = (h > 0)
                        ? (gsize) (write_iter->length / h) * FH_CHANNELS
                        : 0;

        if (written == 0)
          FH_LOG ("[寫回] 第一塊 roi=(%d,%d) %dx%d length=%d(像素) "
                  "每列=%u float 應為 %d",
                  x0, y0, w, h, write_iter->length,
                  (guint) stride, w * FH_CHANNELS);

        if (stride < (gsize) w * FH_CHANNELS)
          {
            FH_LOG ("[致命] 寫入行距 %u 小於每列 %d",
                    (guint) stride, w * 4);
            cancel = TRUE;
            break;
          }

        for (j = 0; j < h; j++)
          {
            gfloat *p = px + (gsize) j * stride;

            for (i = 0; i < w; i++)
              {
                gint   idx = (y0 + j) * width + (x0 + i);
                gfloat ink = dst[idx];

                p[i * 4 + 0] = ink;
                p[i * 4 + 1] = ink;
                p[i * 4 + 2] = ink;
                p[i * 4 + 3] = alpha[idx];
              }
          }

        /* 寫完第一塊後立刻抽樣回讀，確認有沒有真的寫進去 */
        if (written == 0)
          {
            gfloat *p = px;

            FH_LOG ("[寫回] 寫入後第一塊前 5 點 R: "
                    "%.4f %.4f %.4f %.4f %.4f",
                    p[0], p[4], p[8], p[12], p[16]);
          }

        written += h;

        gegl_buffer_iterator_stop (write_iter);

        if (! gimp_progress_update (100.0))
          {
            cancel = TRUE;
            break;
          }
      }

    gimp_progress_end ();

    FH_LOG ("[寫回] 完成，共寫入 %d 列，cancel=%d",
            written, cancel ? 1 : 0);

    g_object_unref (write_iter);
    g_free (alpha);

    g_free (src);
    g_free (dst);

    if (cancel)
      {
        FH_LOG ("[結果] 被取消，回傳 FALSE");
        return FALSE;
      }
  }

  FH_LOG ("[結果] 全部成功，回傳 TRUE");
  return TRUE;
}
