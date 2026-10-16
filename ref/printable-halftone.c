/* GIMP Plug-in "Printable Halftone"
 * Version 1.0. Last modified 2011-02-27 21:21
 *
 * Copyright (C) 2006-2007, 2011 Artturi Tilanterä
 *  <artturi.tilantera@iki.fi>
 * (the "Author").
 *
 * Permission is hereby granted, free of charge, to any person obtaining a
 * copy of this software and associated documentation files (the "Software"),
 * to deal in the Software without restriction, including without limitation
 * the rights to use, copy, modify, merge, publish, distribute, sublicense,
 * and/or sell copies of the Software, and to permit persons to whom the
 * Software is furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included
 * in all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
 * OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL
 * THE AUTHOR BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
 * IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
 * CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
 *
 * Except as contained in this notice, the name of the Author of the
 * Software shall not be used in advertising or otherwise to promote the
 * sale, use or other dealings in this Software without prior written
 * authorization from the Author.
 */

/* Installation:
 * 1. install package libgimp-dev
 * 2. gimptool-2.0 --install plugin.c
 *    (or gimptool-2.0 --install-admin plugin.c)
 */
#include <stdio.h>
#include <string.h>
#include <libgimp/gimp.h>
#include <libgimp/gimpui.h>

#define PROCEDURE_NAME   "gimp_plugin_printable_halftone"
#define DATA_KEY_VALS    "plug_in_printable_halftone"
#define DATA_KEY_UI_VALS "plug_in_printable_halftone_ui"
#define PARASITE_KEY     "plug-in-template-options"
#define BLACK 0
#define WHITE 255
#define LUMINANCES 256
#define SCANLINE_AREA_HEIGHT 64

/*
 ***** RENDERER DATA
 */
/* Temporary bitmap used by the renderer paint black dots on white. */
// TODO: is this still needed?
struct BWBitmap {
	gint x_size;
	gint y_size;
	guchar * pixels;
};

/* Used by the renderer when creating models of the dots */
struct BitmapPixel { 
	gint x_position;
	gint y_position;
	gint distance_from_center;
};

/* a   b    dot_spacing is distance between dots a and b.
 *   c      The actual square grid has dots a, c and e on the same line.
 * d   e    dot_spacing contains last value used before current run
 *          and changes to current value used at list_pixels_of_dot().
 *          list_pixels_of_dot() also resets this if an error occurs. */
static gint dot_spacing = 0;

/* Derived from dot_spacing */
static gint max_dot_width = 0;
static gint dot_center = 0;

/* Contains list of pixels in dot
 * sorted by their distance from the center of the dot.
 * x_position and y_position are from the center of the
 * dot, which is at (0, 0). See dot_center @ list_pixels_of_dot(). */
struct BitmapPixel * pixels_of_dot = NULL;

/* Contents of *pixels_of_dot remain unchanged (in list_pixels_of_dot())
 * if dot_spacing currently used is <= the one used when
 * contents of *pixels_of_dot was generated last time. */
 
/* Number of allocated BitmapPixels in *pixels_of_dot.
 * Size of dot bitmaps in *precalculated_dots. */
static gint pixels_in_dot_bitmap = 0;

/* Number of sorted pixels in *pixels_of_dot. */
static gint max_pixels_in_dot = 0;

/* Source image luminance -> dot size (pixel count) mapping.
 * Set by calibrate_dot_sizes(). */
static gint pixel_count_of_luminance[LUMINANCES];

/* Contains (max_pixels_in_dot + 1) * (max_dot_width * max_dot_width) -sized
 * bitmaps representing dot with each possible size (pixel counts from
 * zero to max_pixels_in_dot). Each byte is one pixel, values:
 * 0 = black (paint black), 1 = white (transparent). */
static guchar * precalculated_dots = NULL;

/* The final result of rendering, which is finally sent
 * back to the GIMP.
 * It's an image containing black dots painted on white background.
 * Only WHITE and BLACK colors are used. */
static struct BWBitmap result_image = { 0, 0, NULL };


/*
 ***** GIMP I/O
 */
static GimpPixelRgn rgn_in, rgn_out;
static guchar * scanlines_out;

/* channels: 1 = grayscale, 2 = grayscale + alpha,
 *           3 = RGB, 4 = RGB + alpha */
static gint channels;

/* Coordinates of upper left and lower right rectangle
 * containing the selection in image in GIMP
 * to be processed. */
static gint area_x1, area_y1,
		   area_x2, area_y2;

static gint ui_value_size = 8;

/* General */
static void query (void);
static void run   (const gchar     * name,
                   gint              nparams,
                   const GimpParam * param,
		           gint            * nreturn_vals,
                   GimpParam       **return_vals);

static gboolean dialog(GimpDrawable * drawable);

//static gboolean dialog (gint32           image_ID,
//                       GimpDrawable       * drawable,
//                       PlugInVals         * vals,
//	                   PlugInImageVals    * image_vals,
//                       PlugInDrawableVals * drawable_vals,
//                       PlugInUIVals       * ui_vals);
static gboolean dialog_image_constraint_func (gint32 image_id, gpointer data);

/* Rendering */
static void render(GimpDrawable * drawable);
static gboolean prepare_dots(const gint new_dot_spacing);
static gint compare_BitmapPixels(const void * a, const void * b);
static gboolean list_pixels_of_dot(const gint new_dot_spacing);
static gint paint_pixel(struct BWBitmap * image, const gint x, const gint y);
static gboolean calibrate_dot_sizes(void);
static gboolean precalculate_dots(void);
static gboolean render2(void);
static void paint_dot(const gint x, const gint y, const gint luminance);
static void send_to_gimp(void);
static void cleanup_precalc(void);

GimpPlugInInfo PLUG_IN_INFO =
{
  NULL,  /* init_proc  */
  NULL,  /* quit_proc  */
  query, /* query_proc */
  run,   /* run_proc   */
};

MAIN()

static void
query (void)
{
  static GimpParamDef args[] =
  {
    {
      GIMP_PDB_INT32,
      "run-mode",
      "Run mode"
    },
    {
      GIMP_PDB_IMAGE,
      "image",
      "Input image"
    },
    {
      GIMP_PDB_DRAWABLE,
      "drawable",
      "Input drawable"
    }
  };

  const gchar * help_string =
    "Models analog halftoning by literally painting black dots "
	"on white background, varying dot size according to the "
	"source lightness. No digital halftoning cells used. "
	"Grid angle is 45 degrees. Size = DPI / LPI * 1.4 . "
	"(1.4 ~= square root of 2) " 
	"Example: Size = 14 produces halftone with 60 LPI on 600 DPI image. "
	"Uses 30% R + 59% G + 11% B grayscale conversion "
	"in RGB images like GIMP does. Preserves alpha channel.";
 
  gimp_install_procedure (
	PROCEDURE_NAME,
    "",
    help_string,
    "Artturi Tilanterä",
    "Artturi Tilanterä",
    "2011",
    "Printable Halftone...",
    "RGB*, GRAY*",
    GIMP_PLUGIN,
    G_N_ELEMENTS (args), 0,
    args, NULL);

  gimp_plugin_menu_register (PROCEDURE_NAME, "<Image>/Filters/Distorts");
}

static void
run (const gchar      *name,
     gint              nparams,
     const GimpParam  *param,
     gint             *nreturn_vals,
     GimpParam       **return_vals)
{
  static GimpParam  values[1];
  GimpPDBStatusType status = GIMP_PDB_SUCCESS;
  GimpRunMode       run_mode;
  GimpDrawable     *drawable;

  /* Setting mandatory output values */
  *nreturn_vals = 1;
  *return_vals  = values;

  values[0].type = GIMP_PDB_STATUS;
  values[0].data.d_status = status;

  /* Getting run_mode - we won't display a dialog if 
   * we are in NONINTERACTIVE mode */
  run_mode = param[0].data.d_int32;

  /*  Get the specified drawable  */
  drawable = gimp_drawable_get (param[2].data.d_drawable);

  switch (run_mode)
    {
    case GIMP_RUN_INTERACTIVE:
      /* Get options last values if needed */
//      gimp_get_data (PROCEDURE_NAME, &bvals);

      /* Display the dialog */
      if (!dialog(drawable))
        return;
      break;

    default:
      break;
    }

  render(drawable);

  gimp_displays_flush();
  gimp_drawable_detach(drawable);

  /*  Finally, set options in the core  */
  if (run_mode == GIMP_RUN_INTERACTIVE)
//    gimp_set_data (PROCEDURE_NAME, &bvals, sizeof (MyBlurVals));

  return;
}

/* User Interface */

static gboolean dialog(GimpDrawable * drawable)
{
	GtkWidget *dialog;
	GtkWidget *main_vbox;
	GtkWidget *main_hbox;
	GtkWidget *frame;
	GtkWidget *size_label;
	GtkWidget *alignment;
	GtkWidget *spinbutton;
	GtkWidget *spinbutton_adj;
	gboolean   run;

	gimp_ui_init ("printable-halftone-ui", FALSE);

	dialog = gimp_dialog_new ("Printable halftone", "printable-halftone-ui",
	                          NULL, 0,
							  NULL,
							  PROCEDURE_NAME,
							  GTK_STOCK_CANCEL, GTK_RESPONSE_CANCEL,
							  GTK_STOCK_OK,     GTK_RESPONSE_OK,
							  NULL);
	main_vbox = gtk_vbox_new (FALSE, 6);
	gtk_container_add (GTK_CONTAINER (GTK_DIALOG (dialog)->vbox), main_vbox);
	gtk_widget_show (main_vbox);
	
	frame = gtk_frame_new (NULL);
	gtk_widget_show (frame);
	gtk_box_pack_start (GTK_BOX (main_vbox), frame, TRUE, TRUE, 0);
	gtk_container_set_border_width (GTK_CONTAINER (frame), 6);

	alignment = gtk_alignment_new (0.5, 0.5, 1, 1);
	gtk_widget_show (alignment);
	gtk_container_add (GTK_CONTAINER (frame), alignment);
	gtk_alignment_set_padding (GTK_ALIGNMENT (alignment), 6, 6, 6, 6);

	main_hbox = gtk_hbox_new (FALSE, 0);
	gtk_widget_show (main_hbox);
	gtk_container_add (GTK_CONTAINER (alignment), main_hbox);

	/* Size label */
	size_label = gtk_label_new_with_mnemonic ("_Size:");
	gtk_widget_show (size_label);
	gtk_box_pack_start (GTK_BOX (main_hbox), size_label, FALSE, FALSE, 6);
	gtk_label_set_justify (GTK_LABEL (size_label), GTK_JUSTIFY_RIGHT);

	/* Spin buttons */
	spinbutton_adj = (GtkWidget *) gtk_adjustment_new (8, 2, 100, 1, 5, 0);
	//spinbutton_adj = (GtkWidget *) gtk_adjustment_new (8, 2, 100, 1, 5, 5);
	spinbutton = gtk_spin_button_new (GTK_ADJUSTMENT (spinbutton_adj), 1, 0);
	gtk_widget_show (spinbutton);
	gtk_box_pack_start (GTK_BOX (main_hbox), spinbutton, FALSE, FALSE, 6);
	gtk_spin_button_set_numeric (GTK_SPIN_BUTTON (spinbutton), TRUE);

	g_signal_connect (spinbutton_adj, "value_changed",
	                  G_CALLBACK (gimp_int_adjustment_update),
					  &ui_value_size);

	gtk_widget_show(dialog);
	
  	run = (gimp_dialog_run (GIMP_DIALOG (dialog)) == GTK_RESPONSE_OK);

	gtk_widget_destroy (dialog);
	return run;
}

static gboolean
dialog_image_constraint_func (gint32    image_id,
                              gpointer  data)
{
  return (gimp_image_base_type (image_id) == GIMP_RGB);
}

/* Rendering */

static void render(GimpDrawable * drawable)
{
  	gimp_drawable_mask_bounds(drawable->drawable_id,
  	        &area_x1, &area_y1,
  	        &area_x2, &area_y2);
	result_image.x_size = area_x2 - area_x1;
	result_image.y_size = area_y2 - area_y1;
 	channels = gimp_drawable_bpp(drawable->drawable_id);
 	gimp_pixel_rgn_init (&rgn_in, drawable, area_x1, area_y1,
 	        result_image.x_size, result_image.y_size, FALSE, FALSE);
 	gimp_pixel_rgn_init (&rgn_out, drawable, area_x1, area_y1,
 	        result_image.x_size, result_image.y_size, TRUE, TRUE);

	if (prepare_dots(ui_value_size) == FALSE) {
		g_message("Printable halftone: Out of memory.");
	} else {
		if (render2() == FALSE) {
			g_message("Printable Halftone: Out of memory.");
		}
	}
 
 	/* Update the modified region */
 	gimp_drawable_flush (drawable);
 	gimp_drawable_merge_shadow (drawable->drawable_id, TRUE);
 	gimp_drawable_update (drawable->drawable_id,
 	                      area_x1, area_y1,
						  result_image.x_size, result_image.y_size);
	cleanup_precalc();
}

/* Private functions */

/*
 * Prepares everything for the actual filtering
 */
static gboolean prepare_dots(const gint new_dot_spacing)
{
	if (list_pixels_of_dot(new_dot_spacing) == FALSE) {
		return FALSE;
	}
	if (calibrate_dot_sizes() == FALSE) {
		return FALSE;
	}
	if (precalculate_dots() == FALSE) {
		return FALSE;
	}
	return TRUE;
}

static gint compare_BitmapPixels(const void * a, const void * b)
{
	struct BitmapPixel * pa = (struct BitmapPixel *)a,
				* pb = (struct BitmapPixel *)b;	
	gint distance_difference = pa->distance_from_center
	        - pb->distance_from_center;
	if (distance_difference > 0) {
		return 1;
	} else if (distance_difference < 0) {
		return -1;
	} else {
		return 0;
	}
}

/*
 * Creates a list of pixels in the dot containing the x and y coordinates
 * and the distance from the center of the dot.
 * Pixels are sorted by their distance. The result is in *pixels_of_dot.
 */
static gboolean list_pixels_of_dot(const gint new_dot_spacing)
{
	/* Create an array of max_dot_width x max_dot_width pixels,
	 * representing bitmap of maximum-sized black dot.
	 * Each pixel contains following information:
	 * x and y position in bitmap and distance from the center
	 * of the bitmap (~= the center of the dot).
	 */
	gint x, y, distance_x, distance_y;
	gint dot_center_squared;
	gint distance;

	if (new_dot_spacing < 2) {
		return FALSE;
	}

	dot_spacing = new_dot_spacing;
	max_dot_width = dot_spacing + 2;
	if (max_dot_width %2 == 0)
		max_dot_width += 1;
	dot_center = (max_dot_width-1)/2;
	dot_center_squared = dot_center * dot_center;
	pixels_in_dot_bitmap = max_dot_width * max_dot_width;

	/* Create a list of pixels in the dot */
	pixels_of_dot = (struct BitmapPixel *) g_realloc(pixels_of_dot,
			pixels_in_dot_bitmap * sizeof(struct BitmapPixel));
	if (pixels_of_dot == NULL) {
		cleanup_precalc();
		return FALSE;
	}

	/* 
	 * Measure pixels' distance from the center of the dot */
	for (y = 0; y < max_dot_width; y++) {
		for (x = 0; x < max_dot_width; x++) {
			distance_x = x - dot_center;
			distance_y = y - dot_center;
			
			/* Since distances are calculated only to sort pixels by
			 * their distance, the square of the distance is enough;
			 * (a > b) <=> (sqrt(a) > sqrt(b)), so no time-consuming
			 * square rooting calculation is required. */
			distance = distance_x * distance_x + distance_y * distance_y;
			if (distance < dot_center_squared) {
				pixels_of_dot[max_pixels_in_dot]
					.x_position = distance_x;
				pixels_of_dot[max_pixels_in_dot]
					.y_position = distance_y;
				pixels_of_dot[max_pixels_in_dot]
					.distance_from_center = distance;
				max_pixels_in_dot++;
			}
		}
	}
	qsort(pixels_of_dot, max_pixels_in_dot, sizeof(struct BitmapPixel),
	      compare_BitmapPixels);

	return TRUE;
}

/*
 * Assigns dot sizes to luminance values.
 * Fills pixel_count_of_luminance.
 * Paints five black dots on bitmap with size of dot_spacing X dot_spacing
 * and white background with four dots on each corner and one at the center,
 * growing dot sizes pixel by pixel and measuring white pixels / all pixels
 * ratio = final luminance.
 */
static gboolean calibrate_dot_sizes(void)
{
	struct BWBitmap test_image;
	gint x, y, image_center;
	gint n, black_pixels_in_bitmap, test_image_size;
	gint shade, previous_shade, dot_pixel_size;
	gint shade_ranges[LUMINANCES], shade_range_dot_sizes[LUMINANCES];
	gint shade_range_count;
	gint luminance, shade_range, range_max, range_min;
	
	test_image.x_size = dot_spacing;
	test_image.y_size = dot_spacing;
	test_image_size = test_image.x_size * test_image.y_size;
	image_center = dot_spacing / 2;
	test_image.pixels = (guchar *) g_malloc(test_image.x_size *
			test_image.y_size);
	if (test_image.pixels == NULL) {
		return FALSE;
	}
	memset(test_image.pixels, WHITE, test_image.x_size * test_image.y_size);	
	/* Go through every dot size (in pixels)
	 * beginning from luminance == 255 (white, dot size == 0)
	 * and mark dot sizes where luminance changes
	 * until luminance == 0 (black) is reached.
	 * So n luminance ranges are found where
	 * luminance(range 0) = white and luminance (range n-1) = black. */
	black_pixels_in_bitmap = 0;
	dot_pixel_size = 0;
	previous_shade = WHITE;
	shade_ranges[0] = 255;
	shade_range_dot_sizes[0] = 0;
	shade_range_count = 1;
	for (dot_pixel_size = 0; dot_pixel_size < max_pixels_in_dot;) {
		x = pixels_of_dot[dot_pixel_size].x_position;
		y = pixels_of_dot[dot_pixel_size].y_position;
		n = paint_pixel(&test_image, x, y);
		n += paint_pixel(&test_image, dot_spacing + x, y);
		n += paint_pixel(&test_image, x, dot_spacing + y);
		n += paint_pixel(&test_image, dot_spacing + x, dot_spacing + y);
		n += paint_pixel(&test_image, image_center + x, image_center + y);
		black_pixels_in_bitmap += n;
		dot_pixel_size++;
		shade = WHITE - WHITE * black_pixels_in_bitmap / test_image_size;
		if (shade < previous_shade) {
			shade_ranges[shade_range_count] = shade;
			shade_range_dot_sizes[shade_range_count] = dot_pixel_size;
			shade_range_count++;
			previous_shade = shade;
		}
		if (shade == 0) {
			break;
		}
	}
	/* Make the luminance ranges overlap so that one range changes
	 * to another at the halfway of both ranges' luminances.
	 * Example: luminances a = 199, b = 142, c = 85.
	 * Range containing luminance b
	 * is from (a + b) / 2 = (199 + 142) / 2 = 170
	 *    to   (b + c) / 2 - 1 = (142 + 85) / 2 - 1 = 112.
	 * After that the sum of all the output luminances
	 * at input luminance = 0..255 is the same as
	 * when output luminances = input luminances.
	 */
	/* last range: white only */
	for (luminance = WHITE, range_min = (shade_ranges[1] + WHITE) / 2;
			luminance > range_min; luminance--) {
		pixel_count_of_luminance[luminance] = 0;
	}
	for (shade_range = 1; shade_range < shade_range_count - 1;
			shade_range++) {
		range_max = (shade_ranges[shade_range - 1] +
		        shade_ranges[shade_range]) / 2;
		range_min = (shade_ranges[shade_range + 1] +
				shade_ranges[shade_range]) / 2;
		for (luminance = range_max; luminance > range_min; luminance--) {
			pixel_count_of_luminance[luminance] =
				shade_range_dot_sizes[shade_range];
		}
	}
	/* first range: black only. */
	for (; luminance >= 0; luminance--) {
		pixel_count_of_luminance[luminance] =
			shade_range_dot_sizes[shade_range];
	}
	g_free(test_image.pixels);	
	return TRUE;
}

/*
 * Tries to paint a black pixel in given bitmap
 * Returns number of white pixels changed to black (1 or 0)
 */
static gint paint_pixel(struct BWBitmap * image, const gint x, const gint y)
{
	gint index;
	if ((x >= 0) && (x < image->x_size) && (y >= 0) && (y < image->y_size)) {
		index = y * image->x_size + x;
		if (image->pixels[index] == WHITE) {
			image->pixels[index] = BLACK;
			return 1;
		}
	}
	return 0;
}

/*
 * Generates precalculated dot images used in actual filtering
 */
static gboolean precalculate_dots(void)
{
	gint luminance, dot_pixel_size, x, y, index, base_index;

	precalculated_dots = (guchar *) g_realloc(precalculated_dots,
	        pixels_in_dot_bitmap * LUMINANCES);
	if (precalculated_dots == NULL) {
		cleanup_precalc();
		return FALSE;
	}

	/* Generate bitmap with white background.
	 * Generally, copy bitmap to next luminance value
	 * and add some black pixels each round. */
	dot_pixel_size = 0;
	base_index = WHITE * pixels_in_dot_bitmap;
	memset(precalculated_dots + base_index, WHITE, pixels_in_dot_bitmap);
	
	for (luminance = WHITE; luminance >= BLACK;
	        luminance--, base_index -= pixels_in_dot_bitmap) {
		while (dot_pixel_size < pixel_count_of_luminance[luminance]) {
			x = dot_center + pixels_of_dot[dot_pixel_size].x_position;
			y = dot_center + pixels_of_dot[dot_pixel_size].y_position;
			index = y * max_dot_width + x;
			precalculated_dots[base_index + index] = BLACK;
			dot_pixel_size++;
		}
		if (luminance > 0) {
			memcpy(precalculated_dots + base_index - pixels_in_dot_bitmap,
			        precalculated_dots + base_index,
			        pixels_in_dot_bitmap);
		}
	}
	return TRUE;
}

/*
 * Does the actual filtering
 */
static gboolean render2(void)
{
	guchar * scanline;
	gint x, y, index;
	gint index_step = dot_spacing * channels;
	guchar luminance;
	gint phase;

	result_image.pixels = (guchar *) g_malloc(result_image.x_size
	                                          * result_image.y_size);
	scanline = (guchar *) g_malloc(result_image.x_size * channels);
	scanlines_out = (guchar *) g_malloc(SCANLINE_AREA_HEIGHT
	                                   * result_image.x_size * channels);
	if (result_image.pixels == NULL || scanline == NULL
		|| scanlines_out == NULL) {
		g_free(result_image.pixels);
		g_free(scanline);
		g_free(scanlines_out);
		return FALSE;
	}
	memset(result_image.pixels, WHITE,
	       result_image.x_size * result_image.y_size);
#if 1
	// yksi for(phase) lisää ei näytä hidastavan huomattavasti
	// gimp_pixel_rgn_get_row vie 70% suoritusajasta
	// pistekoosta riippumatta.
	// optimointi: muuta gimp_pixel_rgn_get_row
	// gimp_pixel_rgb_get_rectiksi, y-koko maks. 64
	//
	// paint_dot vie 10% suoritusajasta (koolla 8)
	//   koolla 6 2x ajan vrt koolla 8
	//   koolla 5 2.5x ajan vrt koolla 8
	//   koolla 4 8x ajan vrt koolla 8
	//   koolla 2 9x ajan vrt koolla 8
	// optimointi hankalaa nimenomaan pienellä pistekoolla
    //
	for (phase = 0; phase < 2; phase++) {
	for (y = phase * dot_spacing / 2;
			y < result_image.y_size; y += dot_spacing) {
		gimp_pixel_rgn_get_row (&rgn_in, scanline, area_x1, area_y1 + y,
		        result_image.x_size);
		for (x = phase * dot_spacing / 2, index = 0; x < result_image.x_size;
		        x += dot_spacing, index += index_step) {
			if (channels < 3) {
				luminance = scanline[index];
			} else {
				luminance = (30 * scanline[index] +
				             59 * scanline[index + 1] +
							 11 * scanline[index + 2]) / 100;
			}
			paint_dot(x, y, luminance);
		}
		gimp_progress_update((gdouble)y / (gdouble)result_image.y_size
		                     * 0.5 + (gdouble)phase * 0.5);
	}
	}
#else
	/* Unoptimized version */

	for (y = 0; y < result_image.y_size; y += dot_spacing) {
		gimp_pixel_rgn_get_row (&rgn_in, scanline, area_x1, area_y1 + y,
		        result_image.x_size);
		for (x = 0, index = 0; x < result_image.x_size;
		        x += dot_spacing, index += index_step) {
			if (channels < 3) {
				luminance = scanline[index];
			} else {
				luminance = (30 * scanline[index] +
				             59 * scanline[index + 1] +
							 11 * scanline[index + 2]) / 100;
			}
			paint_dot(x, y, luminance);
		}
		gimp_progress_update((gdouble)y / (gdouble)result_image.y_size
		                     * 0.5);
	}
	for (y = dot_spacing / 2; y < result_image.y_size; y += dot_spacing) {
		gimp_pixel_rgn_get_row (&rgn_in, scanline, area_x1, area_y1 + y,
		        result_image.x_size);
		for (x = dot_spacing / 2, index = 0; x < result_image.x_size;
		        x += dot_spacing, index += index_step) {
			if (channels < 3) {
				luminance = scanline[index];
			} else {
				luminance = (30 * scanline[index] +
				             59 * scanline[index + 1] +
							 11 * scanline[index + 2]) / 100;
			}
			paint_dot(x, y, luminance);
		}
		gimp_progress_update((gdouble)y / (gdouble)result_image.y_size
		                     * 0.5 + 0.5);
	}
#endif

	g_free(scanline);
	send_to_gimp();
	g_free(result_image.pixels);
	g_free(scanlines_out);
	return TRUE;
}

/*
 * Paints black dots into result_image.
 */
static void paint_dot(const gint x, const gint y, const gint luminance)
{
	/* xi, yi, begin_x, begin_y, end_x, end_y are coordinates
	 * the origin of which is in the center of the dot
	 * (in the both bitmaps precalculated_dots and result_image */

	/* Counters etc. */
	gint in_x, in_y, out_x, out_y;
	gint index_in, index_out;

	/* Beginning and end coordinates for precalculated_dots */
	gint in_x1 = 0;
	gint in_y1 = 0;
	gint in_x2 = max_dot_width;
	gint in_y2 = max_dot_width;

	/* Beginning and end coordinates for result_image */
	gint out_x1 = x - dot_center;
	gint out_y1 = y - dot_center;
	gint out_x2 = out_x1 + max_dot_width;
	gint out_y2 = out_y1 + max_dot_width;
	
	if (out_x1 < 0) {
		in_x1 -= out_x1;
		out_x1 = 0;
	}
	if (out_y1 < 0) {
		in_y1 -= out_y1;
		out_y1 = 0;
	}
	if (out_x2 > result_image.x_size) {
		in_x2 -= out_x2 - result_image.x_size;
		out_x2 = result_image.x_size;
	}
	if (out_y2 > result_image.y_size) {
		in_y2 -= out_y2 - result_image.y_size;
		out_y2 = result_image.y_size;
	}

	/* Original version */
//	for (in_y = in_y1, out_y = out_y1;
//         in_y < in_y2;
//         in_y++, out_y++)
//    {
//		for (in_x = in_x1, out_x = out_x1;
//             in_x < in_x2;
//             in_x++, out_x++)
//        {
//			index_in = luminance * pixels_in_dot_bitmap
//			           + in_y * max_dot_width + in_x;
//
//			index_out = out_y * result_image.x_size + out_x;
//
//			if (precalculated_dots[index_in] == BLACK) {
//				result_image.pixels[index_out] = BLACK;
//			}
//		}
//	}
	/* Optimized version */
	guchar * src = precalculated_dots + luminance * pixels_in_dot_bitmap
                                      + in_y1 * max_dot_width;
	guchar * dest = result_image.pixels + out_y1 * result_image.x_size;
	for (in_y = in_y1; in_y < in_y2; in_y++)
    {
		for (in_x = in_x1, out_x = out_x1;
             in_x < in_x2;
             in_x++, out_x++)
        {
			dest[out_x] = (dest[out_x]) & (src[in_x]);
		}
		src += max_dot_width;
		dest += result_image.x_size;
	}
}

/*
 * Copies result_image to rgn_out, preserves alpha channel.
 */
static void send_to_gimp(void)
{
	gint area_height = SCANLINE_AREA_HEIGHT;
	gint area_size = result_image.x_size * SCANLINE_AREA_HEIGHT;
	gint y_left;
	gint x, y, index1, index2;
	
	for (y = 0, y_left = result_image.y_size;
	        y < result_image.y_size;
			y += area_height, y_left -= area_height) {
		if (y_left < area_height) {
			area_height = y_left;
			area_size = result_image.x_size * SCANLINE_AREA_HEIGHT;
		}
		if (channels != 1) {
			gimp_pixel_rgn_get_rect (&rgn_in, scanlines_out, area_x1, area_y1 + y,
		        result_image.x_size, area_height);
		}
		switch (channels) {
		case 1: /* Greyscale */
			memcpy(scanlines_out, result_image.pixels + y*result_image.x_size,
			        area_size);
			break;
		case 2: /* Greyscale + alpha */
			for (x = 0, index1 = 0, index2 = y * result_image.x_size;
			        x < area_size; x++, index1 += channels, index2++) {
				scanlines_out[index1] = result_image.pixels[index2];
			}
			break;
		case 3: /* RGB */
		case 4: /* RGB + alpha */
			for (x = 0, index1 = 0, index2 = y * result_image.x_size;
			        x < area_size; x++, index1 += channels, index2++) {
				scanlines_out[index1] = result_image.pixels[index2];
				scanlines_out[index1 + 1] = result_image.pixels[index2];
				scanlines_out[index1 + 2] = result_image.pixels[index2];
			}
			break;
		default:
			break;
		}
		gimp_pixel_rgn_set_rect (&rgn_out, scanlines_out, area_x1, area_y1 + y,
		        result_image.x_size, area_height);
	}
}

static void cleanup_precalc(void)
{
	if (pixels_of_dot != NULL) {
		g_free(pixels_of_dot);
		pixels_of_dot = NULL;
		pixels_in_dot_bitmap = 0;
	}
	if (precalculated_dots != NULL) {
		g_free(precalculated_dots);
		precalculated_dots = NULL;
	}
}

