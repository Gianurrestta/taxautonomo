from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('fiscalidad.urls')), # Conectamos las urls de nuestra app fiscal
]

# Seguridad en desarrollo: Permite a Django servir las imágenes subidas por los usuarios
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

