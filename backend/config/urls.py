from django.urls import path

from captures.api import views as cv
from protocols import views as pv

urlpatterns = [
    path("api/protocols/", pv.ProtocolListView.as_view()),
    path("api/protocols/validate/", pv.ProtocolValidateView.as_view()),
    path("api/protocols/<str:name>/", pv.ProtocolDetailView.as_view()),
    path("api/captures/", cv.CaptureListView.as_view()),
    path("api/captures/<int:pk>/", cv.CaptureDetailView.as_view()),
    path("api/captures/<int:pk>/export/", cv.CaptureExportView.as_view()),
    path("api/frames/", cv.FrameListView.as_view()),
    path("api/frames/<int:pk>/", cv.FrameDetailView.as_view()),
    path("api/frames/<int:pk>/index/", cv.FrameIndexView.as_view()),
    path("api/sources/", cv.SourceListView.as_view()),
]
