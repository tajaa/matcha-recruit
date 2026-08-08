import SwiftUI
import PhotosUI

struct IntakeMediaSection: View {
    @Bindable var vm: IntakeViewModel
    @State private var photosPickerItems: [PhotosPickerItem] = []
    @State private var showCamera = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Photos & video").font(.subheadline.bold())

            ScrollView(.horizontal) {
                HStack(spacing: 8) {
                    ForEach(vm.mediaItems) { item in
                        mediaThumb(item)
                    }
                    PhotosPicker(selection: $photosPickerItems, maxSelectionCount: 5, matching: .any(of: [.images, .videos])) {
                        Image(systemName: "photo.badge.plus")
                            .font(.title2)
                            .frame(width: 64, height: 64)
                            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 10))
                    }
                    Button { showCamera = true } label: {
                        Image(systemName: "camera")
                            .font(.title2)
                            .frame(width: 64, height: 64)
                            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 10))
                    }
                }
            }
        }
        .onChange(of: photosPickerItems) { _, items in
            guard !items.isEmpty else { return }
            vm.addPhotoItems(items)
            photosPickerItems = []
        }
        .sheet(isPresented: $showCamera) {
            CameraPicker { image in vm.addCameraImage(image) }
        }
    }

    @ViewBuilder
    private func mediaThumb(_ item: PendingMedia) -> some View {
        ZStack(alignment: .topTrailing) {
            Group {
                if let thumb = item.thumbnail {
                    Image(uiImage: thumb).resizable().scaledToFill()
                } else {
                    Image(systemName: item.mediaType == .video ? "video" : "photo")
                        .frame(width: 64, height: 64)
                }
            }
            .frame(width: 64, height: 64)
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .overlay {
                switch item.state {
                case .uploading: ProgressView().background(.black.opacity(0.3))
                case .failed:
                    ZStack {
                        Color.red.opacity(0.4)
                        Button { vm.retryMedia(id: item.id) } label: {
                            Image(systemName: "arrow.clockwise")
                                .foregroundStyle(.white)
                        }
                    }
                case .done: EmptyView()
                }
            }

            Button {
                vm.removeMedia(id: item.id)
            } label: {
                Image(systemName: "xmark.circle.fill")
                    .foregroundStyle(.white, .black.opacity(0.6))
            }
            .offset(x: 6, y: -6)
        }
    }
}
