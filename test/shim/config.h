/* 佔位檔：GIMP 官方原始碼會 #include "config.h"，
 * 但 Windows 安裝包未提供此檔（由建置系統產生）。
 * 此處僅提供 _() 巨集以取代 stdplugins-intl.h。 */

#ifndef GIMP_SHIM_CONFIG_H
#define GIMP_SHIM_CONFIG_H

#ifndef _
#  define _(String) (String)
#endif

#ifndef N_
#  define N_(String) (String)
#endif

#endif /* GIMP_SHIM_CONFIG_H */
