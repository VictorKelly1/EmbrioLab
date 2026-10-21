from django.urls import path

from apps.personas import views

app_name = 'personas'

urlpatterns = [
    path('<int:pk>/foto/', views.FotoPersonaView.as_view(), name='foto'),
]
