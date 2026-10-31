from django.contrib import admin
from django.urls import path, include
from django.conf import settings  # Importación segura desde django.conf
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('fiscalidad.urls')), # Conexión con tu app fiscal
]

# Servir archivos multimedia en entorno de desarrollo local si DEBUG es True
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

