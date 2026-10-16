#include <libgimp/gimp.h>
#include <gegl.h>
#include <glib/gstdio.h>

#define _(String) (String)

static void
fl_log (const gchar *fmt, ...)
{
  static FILE *fp = NULL;
  va_list      ap;

  if (! fp)
    {
      gchar *path = g_build_filename (g_get_tmp_dir (),
                                      "black2.log", NULL);
      fp = g_fopen (path, "w");
      g_free (path);
    }

  if (! fp)
    return;

  va_start (ap, fmt);
  g_fprintf (fp, fmt, ap);
  va_end (ap);
  g_fprintf (fp, "\n");
  fflush (fp);
}

#define FL(...) fl_log (__VA_ARGS__)

#define PLUG_IN_BINARY "make-black2"
#define PLUG_IN_PROC   "plug-in-make-black2"
#define PLUG_IN_ROLE   "make-black2"


typedef struct _Goat      Goat;
typedef struct _GoatClass GoatClass;

struct _Goat
{
  GimpPlugIn      parent_instance;
};

struct _GoatClass
{
  GimpPlugInClass parent_class;
};


/* Declare local functions.
 */

#define GOAT_TYPE  (goat_get_type ())
#define GOAT (obj) (G_TYPE_CHECK_INSTANCE_CAST ((obj), GOAT_TYPE, Goat))

GType                   goat_get_type         (void);

static GList          * goat_query_procedures (GimpPlugIn           *plug_in);
static GimpProcedure  * goat_create_procedure (GimpPlugIn           *plug_in,
                                               const gchar          *name);

static GimpValueArray * goat_run              (GimpProcedure        *procedure,
                                               GimpRunMode           run_mode,
                                               GimpImage            *image,
                                               GimpDrawable        **drawables,
                                               GimpProcedureConfig  *config,
                                               gpointer              run_data);


G_DEFINE_TYPE (Goat, goat, GIMP_TYPE_PLUG_IN)

GIMP_MAIN (GOAT_TYPE)


static void
goat_class_init (GoatClass *klass)
{
  GimpPlugInClass *plug_in_class = GIMP_PLUG_IN_CLASS (klass);

  plug_in_class->query_procedures = goat_query_procedures;
  plug_in_class->create_procedure = goat_create_procedure;
}

static void
goat_init (Goat *goat)
{
}

static GList *
goat_query_procedures (GimpPlugIn *plug_in)
{
  return g_list_append (NULL, g_strdup (PLUG_IN_PROC));
}

static GimpProcedure *
goat_create_procedure (GimpPlugIn  *plug_in,
                       const gchar *name)
{
  GimpProcedure *procedure = NULL;

  if (! strcmp (name, PLUG_IN_PROC))
    {
      procedure = gimp_image_procedure_new (plug_in, name,
                                            GIMP_PDB_PROC_TYPE_PLUGIN,
                                            goat_run, NULL, NULL);

      gimp_procedure_set_image_types (procedure, "*");
      gimp_procedure_set_sensitivity_mask (procedure,
                                           GIMP_PROCEDURE_SENSITIVE_DRAWABLE);

      gimp_procedure_set_menu_label (procedure, _("驗證：塗黑"));
      gimp_procedure_set_icon_name (procedure, "gimp-grid");
      gimp_procedure_add_menu_path (procedure,
                                    "<Image>/Filters/Development/");

      gimp_procedure_set_documentation (procedure,
                                        _("塗黑"), _("塗黑"),
                                        PLUG_IN_PROC);
      gimp_procedure_set_attribution (procedure,
                                      "test", "test", "2026");
    }

  return procedure;
}

static GimpValueArray *
goat_run (GimpProcedure        *procedure,
          GimpRunMode           run_mode,
          GimpImage            *image,
          GimpDrawable        **drawables,
          GimpProcedureConfig  *config,
          gpointer              run_data)
{
  GimpDrawable      *drawable;
  GimpPDBStatusType  status = GIMP_PDB_SUCCESS;
  gint               x, y, width, height;

  FL ("[1] 進入 goat_run");

  drawable = drawables[0];
  FL ("[2] drawable=%p 名稱=%s", drawable, gimp_item_get_name (GIMP_ITEM (drawable)));

  if (gimp_drawable_mask_intersect (drawable, &x, &y, &width, &height))
    {
      GeglBuffer *buffer;
      GeglBuffer *shadow_buffer;
      GeglRectangle rect;
      const Babl  *format;
      gfloat      *row;
      gint         stride;
      gint         i;

      FL ("[3] mask_intersect 範圍 x=%d y=%d w=%d h=%d", x, y, width, height);

      gegl_init (NULL, NULL);
      FL ("[4] gegl_init 完成");

      buffer        = gimp_drawable_get_buffer (drawable);
      FL ("[5] get_buffer = %p", buffer);

      shadow_buffer = gimp_drawable_get_shadow_buffer (drawable);
      FL ("[6] get_shadow_buffer = %p", shadow_buffer);

      format = babl_format ("R'G'B'A float");
      FL ("[7] babl_format = %p", format);

      if (! buffer || ! shadow_buffer || ! format)
        {
          FL ("[X] 有指標為 NULL，提前結束");
          return gimp_procedure_new_return_values (procedure,
                                                   GIMP_PDB_EXECUTION_ERROR, NULL);
        }

      rect.x = x;
      rect.y = y;
      rect.width  = width;
      rect.height = height;

      /* rowstride 由我們指定：每列 width 個像素 × 4 通道 × sizeof(gfloat) */
      stride = width * 4;
      row    = g_new (gfloat, stride);

      for (i = 0; i < width; i++)
        {
          gfloat *p = row + (gsize) i * 4;

          p[0] = 0.0f;   /* R = 黑 */
          p[1] = 0.0f;   /* G */
          p[2] = 0.0f;   /* B */
          p[3] = 1.0f;   /* A */
        }

      gegl_buffer_set (shadow_buffer, &rect, 0, format,
                       row, stride * (int) sizeof (gfloat));

      FL ("[8] gegl_buffer_set 完成");

      g_free (row);

      g_object_unref (shadow_buffer); /* flushes the shadow tiles */
      FL ("[9] unref shadow_buffer 完成");

      g_object_unref (buffer);
      FL ("[10] unref buffer 完成");

      gimp_drawable_merge_shadow (drawable, TRUE);
      FL ("[11] merge_shadow 完成");

      gimp_drawable_update (drawable, x, y, width, height);
      gimp_displays_flush ();
      FL ("[12] update + flush 完成");

      gegl_exit ();
      FL ("[13] gegl_exit 完成");
    }

  return gimp_procedure_new_return_values (procedure, status, NULL);
}

