
/* ==========================================================================
 * GIMP 外掛骨架
 * ======================================================================== */

typedef struct _FilmHalftonePlugIn      FilmHalftonePlugIn;
typedef struct _FilmHalftonePlugInClass FilmHalftonePlugInClass;

struct _FilmHalftonePlugIn
{
  GimpPlugIn parent_instance;
};

struct _FilmHalftonePlugInClass
{
  GimpPlugInClass parent_class;   /* 必須繼承 GimpPlugInClass，
                                     若用 GObjectClass 會導致類別結構大小不足 */
};

#define FILM_HALFTONE_TYPE (film_halftone_plug_in_get_type ())
G_DEFINE_TYPE (FilmHalftonePlugIn, film_halftone_plug_in, GIMP_TYPE_PLUG_IN)

static GList          *film_halftone_init_procedures (GimpPlugIn *plug_in);
static GimpProcedure  *film_halftone_create_procedure (GimpPlugIn *plug_in,
                                                       const gchar *name);

static void
film_halftone_plug_in_class_init (FilmHalftonePlugInClass *klass)
{
  GimpPlugInClass *plug_in_class = GIMP_PLUG_IN_CLASS (klass);

  /* init_procedures 會在每次啟動時呼叫；query_procedures 只在
   * 安裝或更新外掛後呼叫一次，用於安裝程序，不適合註冊一般程序。 */
  plug_in_class->init_procedures   = film_halftone_init_procedures;
  plug_in_class->create_procedure = film_halftone_create_procedure;
}

static void
film_halftone_plug_in_init (FilmHalftonePlugIn *self)
{
}

static GList *
film_halftone_init_procedures (GimpPlugIn *plug_in)
{
  GList *list = NULL;

  list = g_list_append (list, g_strdup (PLUG_IN_PROC));

  return list;
}

/* 參數防呆：確保數值落在安全範圍內 */
static void
film_halftone_sanitize (FilmHalftoneParams *p)
{
  if (p->frequency    <    1.0) p->frequency    = 40.0;
  if (p->frequency    >  600.0) p->frequency    = 600.0;
  if (p->resolution   <    1.0) p->resolution   = 300.0;
  if (p->resolution   > 4800.0) p->resolution   = 4800.0;
  if (p->shape_amount <    0.0) p->shape_amount = 0.0;
  if (p->shape_amount >    1.0) p->shape_amount = 1.0;
  if (p->stochastic   <    0.0) p->stochastic   = 0.0;
  if (p->stochastic   >    1.0) p->stochastic   = 1.0;
  if (p->grain_scale  <    0.1) p->grain_scale  = 0.1;
  if (p->grain_scale  >    8.0) p->grain_scale  = 8.0;
  if (p->dot_gain     <    0.0) p->dot_gain     = 0.0;
  if (p->dot_gain     >    0.6) p->dot_gain     = 0.6;
  if (p->min_dot      <    0.0) p->min_dot      = 0.0;
  if (p->max_dot      >    1.0) p->max_dot      = 1.0;
  if (p->min_dot > p->max_dot)
    p->min_dot = p->max_dot;

  if (p->dot_shape < 0 || p->dot_shape >= NUM_DOT_SHAPES)
    p->dot_shape = DOT_SHAPE_ROUND;

  if (p->output_mode < 0 || p->output_mode >= NUM_OUTPUT_MODES)
    p->output_mode = OUT_GRAYSCALE;
}

/* 執行半調處理 */
static GimpValueArray *
film_halftone_run (GimpProcedure        *procedure,
                   GimpRunMode           run_mode,
                   GimpImage            *image,
                   GimpDrawable        **drawables,
                   GimpProcedureConfig  *config,
                   gpointer              run_data)
{
  GimpDrawable      *drawable;
  GeglBuffer        *buffer;
  gboolean           success;
  FilmHalftoneParams params;
  GimpValueArray    *return_vals;

  g_object_get (config,
                "frequency",     &params.frequency,
                "resolution",    &params.resolution,
                "dot-shape",     &params.dot_shape,
                "shape-amount",  &params.shape_amount,
                "stochastic",    &params.stochastic,
                "grain-scale",   &params.grain_scale,
                "noise-size",    &params.noise_size,
                "angle",         &params.angle,
                "dot-gain",      &params.dot_gain,
                "min-dot",       &params.min_dot,
                "max-dot",       &params.max_dot,
                "output-mode",   &params.output_mode,
                "antialias",     &params.antialias,
                "seed",          &params.seed,
                NULL);

  film_halftone_sanitize (&params);

  return_vals = gimp_procedure_new_return_values (procedure, GIMP_PDB_SUCCESS,
                                                 NULL);

  drawable = drawables[0];

  if (run_mode == GIMP_RUN_NONINTERACTIVE)
    return gimp_procedure_new_return_values (procedure, GIMP_PDB_SUCCESS,
                                            NULL);

  buffer = gimp_drawable_get_buffer (drawable);

  if (! buffer)
    return return_vals;

  FH_LOG ("=== 執行外掛 ===");
  FH_LOG ("[執行] drawable 名稱=%s",
          gimp_item_get_name (GIMP_ITEM (drawable)));

  /* 在外掛進程中使用 GEGL API 前必須先初始化。
   * GIMP 應用程式本身已完成初始化，但外掛是獨立行程，
   * 若未自行呼叫 gegl_init() 便建立 buffer iterator，會造成崩潰。 */
  FH_LOG ("[gegl] 呼叫 gegl_init()");
  gegl_init (NULL, NULL);
  FH_LOG ("[gegl] gegl_init() 完成");

  /* 整個處理包在 undo group 內，無論成功、失敗或取消都必須成對關閉。
   * 若提早 return 卻留下開著的 group，GIMP 會回報
   * 「left image undo in inconsistent state」並中止。 */
  FH_LOG ("[undo] 開始 undo group");
  gimp_image_undo_group_start (image);

  success = halftone_process_buffer (&params, buffer,
                                     gimp_drawable_get_width (drawable),
                                     gimp_drawable_get_height (drawable));

  FH_LOG ("[undo] 結束 undo group，success=%d", success ? 1 : 0);
  gimp_image_undo_group_end (image);

  FH_LOG ("[gegl] 呼叫 gegl_exit()");
  gegl_exit ();
  FH_LOG ("[gegl] gegl_exit() 完成");

  g_object_unref (buffer);

  if (! success)
    {
      g_object_unref (return_vals);
      return gimp_procedure_new_return_values (procedure, GIMP_PDB_CANCEL,
                                               NULL);
    }

  /* 官方收尾三步：提交變更、通知區域失效、強制重繪。
   * 少了這些，寫入 buffer 的內容不會反映到畫面上。 */
  FH_LOG ("[收尾] merge_shadow / update / flush 開始");
  gimp_drawable_merge_shadow (drawable, TRUE);
  gimp_drawable_update (drawable,
                        0, 0,
                        gimp_drawable_get_width (drawable),
                        gimp_drawable_get_height (drawable));
  gimp_displays_flush ();
  FH_LOG ("[收尾] 完成，正常結束");

  return return_vals;
}

