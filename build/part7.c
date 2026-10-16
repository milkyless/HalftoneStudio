
static GimpProcedure *
film_halftone_create_procedure (GimpPlugIn  *plug_in,
                                const gchar *name)
{
  GimpProcedure *procedure = NULL;

  if (! strcmp (name, PLUG_IN_PROC))
    {
      procedure = gimp_image_procedure_new (plug_in, name,
                                            GIMP_PDB_PROC_TYPE_PLUGIN,
                                            film_halftone_run,
                                            NULL, NULL);

      gimp_procedure_set_image_types (procedure, "RGB*, GRAY*");
      gimp_procedure_set_sensitivity_mask (procedure,
                                           GIMP_PROCEDURE_SENSITIVE_DRAWABLE);

      gimp_procedure_set_menu_label (procedure,
                                     "膠片顆粒半調網點…");
      gimp_procedure_add_menu_path (procedure,
                                    "<Image>/Filters/Development/");

      gimp_procedure_set_documentation (procedure,
                                        "產生用於網版印刷的隨機顆粒半調網點",
                                        "網點位置依藍雜訊自然分佈，而非傳統規則網格。"
                                        "隨機網佔比可於純隨機顆粒與傳統有序網格之間連續調整。",
                                        name);

      gimp_procedure_set_attribution (procedure,
                                      "Film Halftone",
                                      "Film Halftone",
                                      "2026");

      gimp_procedure_set_icon_name (procedure, "gimp-grid");

      /* ---------- ① 網點結構 ---------- */
      gimp_procedure_add_double_argument (procedure, "resolution",
                                          "輸入解析度 (dpi)",
                                          "用於換算網點像素間距",
                                          1.0, 4800.0, 300.0,
                                          GIMP_PARAM_READWRITE);

      gimp_procedure_add_double_argument (procedure, "frequency",
                                          "網點頻率 (lpi)",
                                          "網版印刷常用 25–60，衣網布建議 30–45",
                                          1.0, 600.0, 40.0,
                                          GIMP_PARAM_READWRITE);

      gimp_procedure_add_int_argument (procedure, "dot-shape",
                                       "網點形狀",
                                       "0 圓形、1 方形、2 橢圓。"
                                       "圓形穩定、方形骨架不易糊版、橢圓介於兩者",
                                       0, NUM_DOT_SHAPES - 1, DOT_SHAPE_ROUND,
                                       GIMP_PARAM_READWRITE);

      gimp_procedure_add_double_argument (procedure, "shape-amount",
                                          "網點不規則度",
                                          "0 = 完美幾何形，越大越接近膠片的有機顆粒",
                                          0.0, 1.0, 0.0,
                                          GIMP_PARAM_READWRITE);

      /* ---------- ② 隨機顆粒（核心） ---------- */
      gimp_procedure_add_double_argument (procedure, "stochastic",
                                          "隨機網占比",
                                          "0% = 純隨機顆粒｜100% = 傳統有序網格",
                                          0.0, 1.0, 0.0,
                                          GIMP_PARAM_READWRITE);

      gimp_procedure_add_double_argument (procedure, "grain-scale",
                                          "顆粒粗細",
                                          "以網點間距為倍率，放大或縮小顆粒",
                                          0.1, 8.0, 1.0,
                                          GIMP_PARAM_READWRITE);

      gimp_procedure_add_int_argument (procedure, "noise-size",
                                       "藍噪聲尺寸",
                                       "顆粒圖案的基礎解析度",
                                       16, 256, 64,
                                       GIMP_PARAM_READWRITE);
