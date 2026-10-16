/* ==========================================================================
 * 最小驗證外掛：把整個當前圖層塗成全黑
 *
 * 目的僅為驗證「讀取 buffer → 處理 → 寫回 shadow buffer → 提交變更」
 * 這條通路是否正確，完全不涉及任何網點演算法。
 *
 * 實作方式完全比照 GIMP 官方範例 goat-exercise-c.c：
 *   gegl_init()
 *   gimp_drawable_get_buffer() / get_shadow_buffer()
 *   gegl_buffer_get() / gegl_buffer_set()   ← 自行指定 rowstride，不需猜行距
 *   merge_shadow / update / flush
 *   gegl_exit()
 * ======================================================================== */

#include <libgimp/gimp.h>
#include <gegl.h>

#define BLACK_PROC "plug-in-make-black"

typedef struct _BlackPlugIn      BlackPlugIn;
typedef struct _BlackPlugInClass BlackPlugInClass;

struct _BlackPlugIn
{
  GimpPlugIn parent_instance;
};

struct _BlackPlugInClass
{
  GimpPlugInClass parent_class;
};

#define BLACK_TYPE (black_plug_in_get_type ())
G_DEFINE_TYPE (BlackPlugIn, black_plug_in, GIMP_TYPE_PLUG_IN)

static GList          *black_init_procedures (GimpPlugIn *plug_in);
static GimpProcedure  *black_create_procedure (GimpPlugIn *plug_in,
                                               const gchar *name);
static GimpValueArray *black_run              (GimpProcedure        *procedure,
                                               GimpRunMode           run_mode,
                                               GimpImage            *image,
                                               GimpDrawable        **drawables,
                                               GimpProcedureConfig  *config,
                                               gpointer              run_data);

static void
black_plug_in_class_init (BlackPlugInClass *klass)
{
  GimpPlugInClass *plug_in_class = GIMP_PLUG_IN_CLASS (klass);

  plug_in_class->init_procedures   = black_init_procedures;
  plug_in_class->create_procedure = black_create_procedure;
}

static void
black_plug_in_init (BlackPlugIn *self)
{
}

static GList *
black_init_procedures (GimpPlugIn *plug_in)
{
  return g_list_append (NULL, g_strdup (BLACK_PROC));
}

static GimpProcedure *
black_create_procedure (GimpPlugIn  *plug_in,
                        const gchar *name)
{
  GimpProcedure *procedure = NULL;

  if (! strcmp (name, BLACK_PROC))
    {
      procedure = gimp_image_procedure_new (plug_in, name,
                                            GIMP_PDB_PROC_TYPE_PLUGIN,
                                            black_run, NULL, NULL);

      gimp_procedure_set_image_types (procedure, "*");
      gimp_procedure_set_sensitivity_mask (procedure,
                                           GIMP_PROCEDURE_SENSITIVE_DRAWABLE);
      gimp_procedure_set_menu_label (procedure, "驗證：全部塗黑");
      gimp_procedure_add_menu_path (procedure,
                                    "<Image>/Filters/Development/");
      gimp_procedure_set_icon_name (procedure, "gimp-grid");
    }

  return procedure;
}

static GimpValueArray *
black_run (GimpProcedure        *procedure,
           GimpRunMode           run_mode,
           GimpImage            *image,
           GimpDrawable        **drawables,
           GimpProcedureConfig  *config,
           gpointer              run_data)
{
  GimpDrawable *drawable = drawables[0];
  gint         x, y, width, height;
  gint         stride;
  gfloat      *row;
  gint         j, i;
  const Babl  *format;

  if (! gimp_drawable_mask_intersect (drawable, &x, &y, &width, &height))
    return gimp_procedure_new_return_values (procedure, GIMP_PDB_CANCEL, NULL);

  /* 黑色、線性 RGBA 四通道 float */
  format = babl_format ("R'G'B'A float");

  /* 每列的 float 數量：寬度 × 4 通道。這裡由我們自行指定，
   * GEGL 依此填入目標緩衝，因此不需要猜測實際的記憶體行距。 */
  stride = width * 4;
  row    = g_new (gfloat, stride);

  gegl_init (NULL, NULL);

  {
    GeglBuffer *buffer        = gimp_drawable_get_buffer (drawable);
    GeglBuffer *shadow_buffer = gimp_drawable_get_shadow_buffer (drawable);
    GeglRectangle rect;

    rect.x = x;
    rect.y = y;
    rect.width  = width;
    rect.height = height;

    /* 整層塗黑（保留 alpha 為 1） */
    for (j = 0; j < height; j++)
      for (i = 0; i < width; i++)
        {
          gfloat *p = row + (gsize) i * 4;

          p[0] = 0.0f;   /* R = 黑 */
          p[1] = 0.0f;   /* G */
          p[2] = 0.0f;   /* B */
          p[3] = 1.0f;   /* A = 不透明 */
        }

    gegl_buffer_set (shadow_buffer, &rect, 0, format,
                     row, stride * (int) sizeof (gfloat));

    g_object_unref (shadow_buffer);   /* flushes the shadow tiles */
    g_object_unref (buffer);
  }

  g_free (row);

  gimp_drawable_merge_shadow (drawable, TRUE);
  gimp_drawable_update (drawable, x, y, width, height);
  gimp_displays_flush ();

  gegl_exit ();

  return gimp_procedure_new_return_values (procedure, GIMP_PDB_SUCCESS, NULL);
}

GIMP_MAIN (BLACK_TYPE)
