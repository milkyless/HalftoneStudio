; GIMP 3 的 Script-Fu：先切換 v3 約定
(script-fu-use-v3)
(gimp-message-set-handler ERROR-CONSOLE)

(define (msg s) (gimp-message s))

(define (make-gradient path)
  (let* ((img   (gimp-image-new 400 300 RGB))
         (layer (gimp-layer-new img "bg" 400 300 RGB-IMAGE 100
                               LAYER-MODE-NORMAL))
         (x 0))
    (gimp-image-insert-layer img layer 0 0)
    (while (< x 400)
      (let ((v (inexact->exact (round (* 255 (/ x 399.0)))))
            (y 0))
        (while (< y 300)
          (gimp-drawable-set-pixel layer x y (list v v v))
          (set! y (+ y 1))))
      (set! x (+ x 1)))
    (gimp-file-save RUN-NONINTERACTIVE img path -1)
    layer))

; Script-Fu 會自動帶入 image 與 drawables，故只傳 14 個參數
(define (halftone stoch shape-amt out-mode)
  (gimp-film-halftone 300.0 40.0 0 shape-amt stoch 1.0 64 15.0
                      0.15 0.03 0.95 out-mode 1 0))

(define (test-case tag stoch shape-amt out-mode)
  (let* ((dir  "C:/Users/Milky/Desktop/Z/test/")
         (lay  (make-gradient (string-append dir "test_src.png")))
         (img  (gimp-item-get-image lay))
         (path (string-append dir (string-append "out_" tag ".png"))))
    (halftone stoch shape-amt out-mode)
    (gimp-file-save RUN-NONINTERACTIVE img path -1)
    (msg (string-append "RESULT " tag " ok"))
    (gimp-image-delete img)))

(msg "TEST START")

(test-case "stoch00"  0.0 0.0 0)
(test-case "stoch50"  0.5 0.0 0)
(test-case "stoch100" 1.0 0.0 0)
(test-case "organic"  0.2 0.6 0)
(test-case "binary"   0.0 0.0 1)

(msg "ALL TESTS DONE")
