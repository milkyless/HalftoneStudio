
      /* ---------- ③ 網屏角度 ---------- */
      gimp_procedure_add_double_argument (procedure, "angle",
                                          "網屏角度 (度)",
                                          "隨機網模式下幾乎不需要；隨機占比調高時才明顯",
                                          0.0, 90.0, 15.0,
                                          GIMP_PARAM_READWRITE);

      /* ---------- ④ 印刷補償 ---------- */
      gimp_procedure_add_double_argument (procedure, "dot-gain",
                                          "網點擴大補償",
                                          "網版印刷油墨擴張補償，常規 10–25%",
                                          0.0, 0.6, 0.15,
                                          GIMP_PARAM_READWRITE);

      gimp_procedure_add_double_argument (procedure, "min-dot",
                                          "最小網點",
                                          "保留暗部細節，過小會糊成一片",
                                          0.0, 1.0, 0.03,
                                          GIMP_PARAM_READWRITE);

      gimp_procedure_add_double_argument (procedure, "max-dot",
                                          "最大網點",
                                          "避免高光死黑",
                                          0.0, 1.0, 0.95,
                                          GIMP_PARAM_READWRITE);

      /* ---------- ⑤ 輸出 ---------- */
      gimp_procedure_add_int_argument (procedure, "output-mode",
                                       "輸出模式",
                                       "0 灰階網點（預覽用）、1 二值（實際製版）、2 反相",
                                       0, NUM_OUTPUT_MODES - 1, OUT_GRAYSCALE,
                                       GIMP_PARAM_READWRITE);

      gimp_procedure_add_boolean_argument (procedure, "antialias",
                                           "邊緣抗鋸齒",
                                           "網點邊緣灰階過渡，提升印刷還原度",
                                           TRUE,
                                           GIMP_PARAM_READWRITE);

      gimp_procedure_add_int_argument (procedure, "seed",
                                       "隨機種子",
                                       "相同種子可重現結果，方便微調單一參數",
                                       0, 1000000, 0,
                                       GIMP_PARAM_READWRITE);
    }

  return procedure;
}

GIMP_MAIN (FILM_HALFTONE_TYPE)
