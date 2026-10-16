;; 觸發 film-halftone，驗證診斷日誌是否會產生
(let* ((img (car (gimp-image-new 120 90 RGB)))
       (layer (car (gimp-layer-new img 120 90 RGB-IMAGE "test" 100 LAYER-MODE-NORMAL))))
  (gimp-image-insert-layer img layer 0 0)
  (gimp-drawable-fill layer FILL-WHITE)
  (gimp-image-flatten img)
  (gimp-displays-flush)
  (gimp-item-set-name (car (gimp-image-get-active-drawable img)) "flat")
  (let ((res (gimp-procedural-db-proc-call "film-halftone"
                                           1 1 1 1 1 1 1 1 1 1 1 1 1 1 1
                                           (car (gimp-image-get-active-drawable img)))))
    (gimp-message (string-append "CALL DONE")))
(gimp-quit 0)
