import SwiftUI

private struct ErrorText: View {
    let message: String?
    var body: some View {
        if let message, !message.isEmpty {
            Text(message).font(.footnote).foregroundStyle(.red).frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

private struct ProductImage: View {
    let product: Product
    var height: CGFloat = 170

    var body: some View {
        AsyncImage(url: product.imageURL) { phase in
            if let image = phase.image {
                image.resizable().scaledToFill()
            } else {
                ZStack {
                    Color.green.opacity(0.09)
                    Image(systemName: "leaf.fill").font(.largeTitle).foregroundStyle(.green.opacity(0.6))
                }
            }
        }
        .frame(maxWidth: .infinity)
        .frame(height: height)
        .clipped()
    }
}

struct HomeView: View {
    @EnvironmentObject private var catalog: CatalogStore
    @State private var category: String?

    private var categories: [String] {
        Array(Set(catalog.products.compactMap(\.category))).sorted().prefix(8).map { $0 }
    }

    private var shown: [Product] {
        guard let category else { return catalog.products }
        return catalog.products.filter { $0.category == category }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                VStack(alignment: .leading, spacing: 5) {
                    Text(Config.current.displayName).font(.largeTitle.bold())
                    Text(Config.current.tagline).foregroundStyle(.secondary)
                }
                .padding(.horizontal)

                if !categories.isEmpty {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack {
                            categoryChip("Everything", selected: category == nil) { category = nil }
                            ForEach(categories, id: \.self) { value in
                                categoryChip(value, selected: category == value) { category = value }
                            }
                        }
                        .padding(.horizontal)
                    }
                }

                if catalog.isLoading && catalog.products.isEmpty {
                    ProgressView().frame(maxWidth: .infinity).padding(.top, 80)
                } else {
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 155), spacing: 14)], spacing: 14) {
                        ForEach(shown) { product in
                            NavigationLink(value: product) { ProductCard(product: product) }
                                .buttonStyle(.plain)
                        }
                    }
                    .padding(.horizontal)
                }

                ErrorText(message: catalog.errorMessage).padding(.horizontal)
                if !catalog.posts.isEmpty { BlogStrip(posts: Array(catalog.posts.prefix(5))) }
            }
            .padding(.vertical)
        }
        .refreshable { await catalog.load() }
        .navigationDestination(for: Product.self) { ProductDetailView(product: $0) }
        .navigationTitle("Shop")
        .navigationBarTitleDisplayMode(.inline)
    }

    private func categoryChip(_ label: String, selected: Bool, action: @escaping () -> Void) -> some View {
        Button(label, action: action)
            .font(.subheadline.weight(.medium))
            .padding(.horizontal, 13).padding(.vertical, 8)
            .background(selected ? Color.green : Color.secondary.opacity(0.12), in: Capsule())
            .foregroundStyle(selected ? .white : .primary)
    }
}

private struct ProductCard: View {
    let product: Product
    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            ProductImage(product: product, height: 145).clipShape(RoundedRectangle(cornerRadius: 14))
            Text(product.name).font(.headline).lineLimit(2)
            Text(money(product.displayPriceCents, product.currency)).font(.subheadline.weight(.semibold)).foregroundStyle(.green)
            if !product.subscriptionIntervals.isEmpty {
                Text("Subscribe & save").font(.caption).foregroundStyle(.secondary)
            }
        }
    }
}

struct ProductDetailView: View {
    let product: Product
    @EnvironmentObject private var cart: CartStore
    @EnvironmentObject private var favorites: FavoritesStore
    @EnvironmentObject private var router: AppRouter
    @State private var selected = Set<String>()
    @State private var interval = "once"
    @State private var showAdded = false

    private var selectionsValid: Bool {
        product.optionGroups.allSatisfy { !$0.required || $0.options.contains(where: { selected.contains($0.id) }) }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                ProductImage(product: product, height: 330)
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 5) {
                        Text(product.name).font(.title2.bold())
                        Text(money(product.displayPriceCents, product.currency)).font(.title3.weight(.semibold)).foregroundStyle(.green)
                    }
                    Spacer()
                    Button {
                        Task { await favorites.toggle(product.id) }
                    } label: {
                        Image(systemName: favorites.contains(product.id) ? "heart.fill" : "heart")
                            .font(.title2).foregroundStyle(.red)
                    }
                    .accessibilityLabel(favorites.contains(product.id) ? "Remove from saved items" : "Save item")
                }
                if let description = product.description { Text(description).foregroundStyle(.secondary) }

                ForEach(product.optionGroups) { group in
                    VStack(alignment: .leading, spacing: 9) {
                        Text(group.name + (group.required ? " *" : "")).font(.headline)
                        ForEach(group.options) { option in
                            let isSelected = selected.contains(option.id)
                            Button {
                                if group.selectType == "single" {
                                    selected.subtract(group.options.map(\.id))
                                    selected.insert(option.id)
                                } else if isSelected {
                                    selected.remove(option.id)
                                } else {
                                    selected.insert(option.id)
                                }
                            } label: {
                                HStack {
                                    Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                                    Text(option.name)
                                    Spacer()
                                    if option.priceDeltaCents != 0 {
                                        Text((option.priceDeltaCents > 0 ? "+" : "") + money(option.priceDeltaCents, product.currency))
                                    }
                                }
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding().background(.thinMaterial, in: RoundedRectangle(cornerRadius: 14))
                }

                if !product.subscriptionIntervals.isEmpty {
                    Picker("Purchase", selection: $interval) {
                        Text("One time").tag("once")
                        ForEach(product.subscriptionIntervals, id: \.self) { value in
                            Text(value == "week" ? "Weekly" : "Monthly").tag(value)
                        }
                    }
                    .pickerStyle(.segmented)
                    if interval != "once", product.subscriptionDiscountBps > 0 {
                        Text("Includes \(Double(product.subscriptionDiscountBps) / 100, specifier: "%.0f")% subscription savings")
                            .font(.footnote).foregroundStyle(.green)
                    }
                }

                Button {
                    cart.add(
                        product: product,
                        selectedOptionIds: Array(selected),
                        interval: interval == "once" ? nil : interval
                    )
                    showAdded = true
                } label: {
                    Label(showAdded ? "Added" : "Add to cart", systemImage: showAdded ? "checkmark" : "bag.badge.plus")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent).tint(.green)
                .disabled(!selectionsValid || product.inventory == 0)

                if showAdded {
                    Button("View cart") { router.selectedTab = .cart }
                        .frame(maxWidth: .infinity)
                }
            }
            .padding(.bottom, 24)
        }
        .navigationTitle(product.name)
        .navigationBarTitleDisplayMode(.inline)
        .task {
            for group in product.optionGroups where group.required {
                if let first = group.options.first { selected.insert(first.id) }
            }
        }
    }
}

struct CartView: View {
    @EnvironmentObject private var catalog: CatalogStore
    @EnvironmentObject private var cart: CartStore
    @State private var quote: Quote?
    @State private var quoteError: String?

    var body: some View {
        List {
            if cart.lines.isEmpty {
                ContentUnavailableView("Your cart is empty", systemImage: "bag", description: Text("Add something good from the shop."))
            }
            ForEach(cart.lines) { line in
                if let product = catalog.product(line.productId) {
                    HStack(spacing: 12) {
                        ProductImage(product: product, height: 64).frame(width: 64).clipShape(RoundedRectangle(cornerRadius: 10))
                        VStack(alignment: .leading) {
                            Text(product.name).font(.headline)
                            Text(line.interval.map { "Every \($0)" } ?? "One time").font(.caption).foregroundStyle(.secondary)
                            Stepper("Qty \(line.quantity)", value: Binding(
                                get: { line.quantity },
                                set: { cart.setQuantity(for: line.id, quantity: $0) }
                            ), in: 1...10_000)
                            .font(.caption)
                        }
                    }
                    .swipeActions { Button("Remove", role: .destructive) { cart.remove(line.id) } }
                }
            }
            if let quote {
                Section("Total") {
                    totalRow("Items", quote.subtotalCents, quote.currency)
                    totalRow("Tax", quote.taxCents, quote.currency)
                    totalRow("Shipping", quote.shippingCents, quote.currency)
                    totalRow("Total", quote.totalCents, quote.currency, bold: true)
                }
            }
            ErrorText(message: quoteError)
            if !cart.lines.isEmpty {
                NavigationLink("Continue to checkout") { CheckoutView() }
                    .buttonStyle(.borderedProminent)
            }
        }
        .navigationTitle("Cart")
        .task(id: cart.lines) { await refreshQuote() }
    }

    private func totalRow(_ label: String, _ cents: Int, _ currency: String, bold: Bool = false) -> some View {
        HStack { Text(label); Spacer(); Text(money(cents, currency)) }
            .fontWeight(bold ? .bold : .regular)
    }

    private func refreshQuote() async {
        guard !cart.lines.isEmpty else { quote = nil; return }
        do {
            quote = try await CheckoutService.shared.quote(lines: cart.lines)
            quoteError = quote?.lines.contains(where: { !$0.available }) == true ? "One or more items are no longer available." : nil
        } catch { quoteError = error.localizedDescription }
    }
}

struct CheckoutView: View {
    @EnvironmentObject private var session: SessionStore
    @EnvironmentObject private var cart: CartStore
    @EnvironmentObject private var router: AppRouter
    @State private var addresses: [Address] = []
    @State private var selectedAddress: String?
    @State private var isWorking = false
    @State private var message: String?
    @State private var completedOrder: Order?
    @State private var guestEmail = ""
    @State private var guestName = ""

    private var isRecurring: Bool { cart.lines.contains { $0.interval != nil } }
    private var guestEmailValid: Bool {
        let parts = guestEmail.split(separator: "@")
        return parts.count == 2 && parts[1].contains(".")
    }

    var body: some View {
        Form {
            if session.shopper == nil {
                if isRecurring {
                    Section {
                        Text("Sign in to start a subscription and manage renewals.")
                        NavigationLink("Sign in") { LoginView() }
                    }
                } else {
                    Section("Guest checkout") {
                        TextField("Email", text: $guestEmail)
                            .textInputAutocapitalization(.never).keyboardType(.emailAddress)
                        TextField("Name (optional)", text: $guestName)
                        NavigationLink("Sign in instead") { LoginView() }
                    }
                }
            } else {
                if !addresses.isEmpty {
                    Section("Shipping address") {
                        Picker("Address", selection: $selectedAddress) {
                            ForEach(addresses) { address in
                                Text(address.label ?? address.line1).tag(address.id)
                            }
                        }
                    }
                }
            }
            Section {
                Button {
                    Task { await beginCheckout() }
                } label: {
                    if isWorking { ProgressView().frame(maxWidth: .infinity) }
                    else { Text("Open secure checkout").frame(maxWidth: .infinity) }
                }
                .disabled(isWorking || cart.lines.isEmpty ||
                          (session.shopper == nil && (isRecurring || !guestEmailValid)))
            }
            ErrorText(message: message)
            if let completedOrder {
                Section("Order") { OrderSummary(order: completedOrder) }
            }
        }
        .navigationTitle("Checkout")
        .task { await loadAddresses() }
    }

    private func loadAddresses() async {
        guard session.shopper != nil else { return }
        addresses = (try? await StorefrontAPI.shared.request(Config.current.shopperPath + "/me/addresses")) ?? []
        selectedAddress = addresses.first(where: \.isDefault)?.id ?? addresses.first?.id
    }

    private func beginCheckout() async {
        isWorking = true
        defer { isWorking = false }
        do {
            if let selectedAddress,
               let address = addresses.first(where: { $0.id == selectedAddress }),
               !address.isDefault {
                var updated = address
                updated.isDefault = true
                let _: Address = try await StorefrontAPI.shared.request(
                    Config.current.shopperPath + "/me/addresses/\(selectedAddress)", method: "PATCH", body: updated.requestObject
                )
            }
            let checkout = try await CheckoutService.shared.checkout(
                lines: cart.lines,
                shopper: session.shopper,
                guestEmail: session.shopper == nil ? guestEmail.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() : nil,
                guestName: session.shopper == nil ? guestName.nilIfEmpty : nil
            )
            guard checkout.checkoutUrl != nil else {
                message = "This order was sent to the store for manual payment."
                cart.clear()
                return
            }
            let result = try await CheckoutService.shared.openHostedCheckout(checkout)
            guard let result else { return }
            guard result == .success else {
                message = "Checkout canceled. Your cart is still here."
                return
            }
            if checkout.subscriptionId != nil {
                message = "Subscription started. It may take a moment to appear in your account."
                cart.clear()
                router.selectedTab = .account
            } else {
                completedOrder = try await CheckoutService.shared.waitForOrder(token: checkout.orderToken)
                cart.clear()
            }
        } catch { message = error.localizedDescription }
    }
}

struct LoginView: View {
    @EnvironmentObject private var session: SessionStore
    @Environment(\.dismiss) private var dismiss
    @State private var email = ""
    @State private var code = ""
    @State private var sent = false

    var body: some View {
        Form {
            Section(sent ? "Enter the six-digit code" : "Email") {
                TextField("you@example.com", text: $email).textContentType(.emailAddress).textInputAutocapitalization(.never).disabled(sent)
                if sent {
                    TextField("123456", text: $code).keyboardType(.numberPad).textContentType(.oneTimeCode)
                    Button("Verify and sign in") {
                        Task { if await session.verify(email: email, code: code) { dismiss() } }
                    }
                    .disabled(code.count != 6 || session.isWorking)
                } else {
                    Button("Send code") { Task { sent = await session.requestCode(email: email) } }
                        .disabled(email.isEmpty || session.isWorking)
                }
            }
            ErrorText(message: session.errorMessage)
        }
        .navigationTitle("Sign in")
    }
}

struct SavedItemsView: View {
    @EnvironmentObject private var catalog: CatalogStore
    @EnvironmentObject private var favorites: FavoritesStore
    private var products: [Product] { catalog.products.filter { favorites.contains($0.id) } }

    var body: some View {
        Group {
            if products.isEmpty {
                ContentUnavailableView("Nothing saved yet", systemImage: "heart", description: Text("Tap the heart on a product to keep it here."))
            } else {
                List(products) { product in
                    NavigationLink(value: product) {
                        HStack { ProductImage(product: product, height: 54).frame(width: 54).clipShape(RoundedRectangle(cornerRadius: 9)); Text(product.name) }
                    }
                }
            }
        }
        .navigationTitle("Saved")
        .navigationDestination(for: Product.self) { ProductDetailView(product: $0) }
    }
}

struct AccountHomeView: View {
    @EnvironmentObject private var session: SessionStore

    var body: some View {
        Group {
            if let shopper = session.shopper {
                List {
                    Section {
                        Text(shopper.name?.isEmpty == false ? shopper.name! : shopper.email).font(.headline)
                        Text(shopper.email).font(.caption).foregroundStyle(.secondary)
                    }
                    Section {
                        NavigationLink("Orders") { OrdersView(initialToken: nil) }
                        NavigationLink("Addresses") { AddressesView() }
                        NavigationLink("Subscriptions") { SubscriptionsView() }
                        NavigationLink("Notifications") { NotificationSettingsView() }
                        NavigationLink("Account settings") { AccountSettingsView() }
                    }
                    Button("Sign out", role: .destructive) { Task { await session.logout() } }
                }
            } else {
                ContentUnavailableView {
                    Label("Your account", systemImage: "person.crop.circle")
                } description: {
                    Text("Sign in for order history, saved addresses, and subscriptions.")
                } actions: {
                    NavigationLink("Sign in") { LoginView() }.buttonStyle(.borderedProminent).tint(.green)
                }
            }
        }
        .navigationTitle("Account")
    }
}

struct OrdersView: View {
    let initialToken: String?
    @State private var orders: [Order] = []
    @State private var linked: Order?
    @State private var nextCursor: String?
    @State private var isLoading = false
    @State private var errorMessage: String?

    var body: some View {
        List {
            if let linked { Section("Opened order") { OrderSummary(order: linked) } }
            ForEach(orders) { OrderSummary(order: $0) }
            if nextCursor != nil {
                Button(isLoading ? "Loading…" : "Load more") { Task { await loadPage() } }
                    .disabled(isLoading)
            }
            ErrorText(message: errorMessage)
        }
        .overlay { if orders.isEmpty && linked == nil && errorMessage == nil { ProgressView() } }
        .navigationTitle("Orders")
        .task {
            if let token = initialToken {
                linked = try? await StorefrontAPI.shared.request("/public/orders/\(token)", authenticated: false)
            }
            await loadPage(reset: true)
        }
    }

    private func loadPage(reset: Bool = false) async {
        guard !isLoading else { return }
        if !reset && nextCursor == nil { return }
        isLoading = true
        defer { isLoading = false }
        do {
            var path = Config.current.shopperPath + "/me/orders"
            if !reset, let cursor = nextCursor {
                var query = URLComponents()
                query.queryItems = [URLQueryItem(name: "cursor", value: cursor)]
                path += "?\(query.percentEncodedQuery ?? "")"
            }
            let page: OrderPage = try await StorefrontAPI.shared.request(path)
            orders = reset ? page.orders : orders + page.orders
            nextCursor = page.nextCursor
            errorMessage = nil
        } catch { errorMessage = error.localizedDescription }
    }
}

private struct OrderSummary: View {
    let order: Order
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack { Text(order.status.capitalized).font(.headline); Spacer(); if let total = order.totalCents { Text(money(total, order.currency)) } }
            ForEach(order.items) { item in Text("\(item.quantity) × \(item.title)").font(.subheadline).foregroundStyle(.secondary) }
            if let tracking = order.trackingNumber { Text("Tracking: \(tracking)").font(.caption) }
            if let token = order.orderToken,
               let url = URL(string: Config.current.apiBase.absoluteString + "/public/orders/\(token)/receipt.pdf") {
                Link("Receipt PDF", destination: url).font(.caption)
            }
        }
        .padding(.vertical, 4)
    }
}

struct AddressesView: View {
    @State private var rows: [Address] = []
    @State private var editing: Address?
    @State private var errorMessage: String?

    var body: some View {
        List {
            ForEach(rows) { address in
                Button { editing = address } label: {
                    VStack(alignment: .leading) {
                        Text(address.label ?? address.name).font(.headline)
                        Text("\(address.line1), \(address.city) \(address.postalCode)").font(.caption).foregroundStyle(.secondary)
                        if address.isDefault { Text("Default").font(.caption2).foregroundStyle(.green) }
                    }
                }
                .swipeActions { Button("Delete", role: .destructive) { Task { await remove(address) } } }
            }
            ErrorText(message: errorMessage)
        }
        .navigationTitle("Addresses")
        .toolbar { Button { editing = Address() } label: { Image(systemName: "plus") } }
        .sheet(item: $editing) { value in AddressEditor(address: value) { await save($0) } }
        .task { await load() }
    }

    private func load() async {
        do { rows = try await StorefrontAPI.shared.request(Config.current.shopperPath + "/me/addresses") }
        catch { errorMessage = error.localizedDescription }
    }

    private func save(_ address: Address) async -> Bool {
        do {
            if let id = address.id {
                let value: Address = try await StorefrontAPI.shared.request(Config.current.shopperPath + "/me/addresses/\(id)", method: "PATCH", body: address.requestObject)
                rows = rows.map { $0.id == id ? value : $0 }
                if value.isDefault { rows = rows.map { row in var copy = row; copy.isDefault = row.id == value.id; return copy } }
            } else {
                let value: Address = try await StorefrontAPI.shared.request(Config.current.shopperPath + "/me/addresses", method: "POST", body: address.requestObject)
                if value.isDefault { rows = rows.map { row in var copy = row; copy.isDefault = false; return copy } }
                rows.insert(value, at: 0)
            }
            return true
        } catch { errorMessage = error.localizedDescription; return false }
    }

    private func remove(_ address: Address) async {
        guard let id = address.id else { return }
        do {
            let _: Empty = try await StorefrontAPI.shared.request(Config.current.shopperPath + "/me/addresses/\(id)", method: "DELETE")
            rows.removeAll { $0.id == id }
        } catch { errorMessage = error.localizedDescription }
    }
}

private struct AddressEditor: View {
    @Environment(\.dismiss) private var dismiss
    @State var address: Address
    let save: (Address) async -> Bool
    @State private var working = false

    var body: some View {
        NavigationStack {
            Form {
                TextField("Label", text: optionalBinding($address.label))
                TextField("Full name", text: $address.name)
                TextField("Address", text: $address.line1)
                TextField("Address line 2", text: optionalBinding($address.line2))
                TextField("City", text: $address.city)
                TextField("State or region", text: optionalBinding($address.region))
                TextField("Postal code", text: $address.postalCode)
                TextField("Country code", text: $address.country).textInputAutocapitalization(.characters)
                TextField("Phone", text: optionalBinding($address.phone)).keyboardType(.phonePad)
                Toggle("Default address", isOn: $address.isDefault)
            }
            .navigationTitle(address.id == nil ? "New address" : "Edit address")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { Task { working = true; if await save(address) { dismiss() }; working = false } }
                        .disabled(working || address.name.isEmpty || address.line1.isEmpty || address.city.isEmpty || address.postalCode.isEmpty)
                }
            }
        }
    }
}

struct SubscriptionsView: View {
    @State private var rows: [Subscription] = []
    @State private var errorMessage: String?

    var body: some View {
        List {
            ForEach(rows) { subscription in
                VStack(alignment: .leading, spacing: 7) {
                    Text(subscription.items.map { "\($0.quantity) × \($0.title)" }.joined(separator: ", ")).font(.headline)
                    Text("\(money(subscription.totalCents, subscription.currency)) / \(subscription.interval) · \(subscription.status)").font(.caption).foregroundStyle(.secondary)
                    if subscription.cancelAtPeriodEnd {
                        Button("Resume") { Task { await change(subscription, cancel: false) } }
                    } else if !["canceled", "incomplete_expired"].contains(subscription.status) {
                        Button("Cancel at period end", role: .destructive) { Task { await change(subscription, cancel: true) } }
                    }
                }
            }
            ErrorText(message: errorMessage)
        }
        .navigationTitle("Subscriptions")
        .task { await load() }
    }

    private func load() async {
        do { rows = try await StorefrontAPI.shared.request(Config.current.shopperPath + "/me/subscriptions") }
        catch { errorMessage = error.localizedDescription }
    }

    private func change(_ subscription: Subscription, cancel: Bool) async {
        do {
            let _: Empty = try await StorefrontAPI.shared.request(
                Config.current.shopperPath + "/me/subscriptions/\(subscription.id)/\(cancel ? "cancel" : "resume")",
                method: "POST"
            )
            await load()
        } catch { errorMessage = error.localizedDescription }
    }
}

struct NotificationSettingsView: View {
    @EnvironmentObject private var session: SessionStore
    @State private var enabled = true
    @State private var errorMessage: String?

    var body: some View {
        Form {
            Toggle("Order updates", isOn: $enabled)
                .onChange(of: enabled) { _, value in
                    Task {
                        do {
                            try await session.update(name: session.shopper?.name, phone: session.shopper?.phone, pushOrderUpdates: value)
                            if value { await NotificationService.shared.requestAuthorization(); await NotificationService.shared.registerCurrentDevice() }
                        } catch { errorMessage = error.localizedDescription }
                    }
                }
            Text("Get paid, shipped, fulfilled, declined, and renewal status on this device.").font(.footnote).foregroundStyle(.secondary)
            ErrorText(message: errorMessage)
        }
        .navigationTitle("Notifications")
        .onAppear { enabled = session.shopper?.pushOrderUpdates ?? true }
    }
}

struct AccountSettingsView: View {
    @EnvironmentObject private var session: SessionStore
    @Environment(\.dismiss) private var dismiss
    @State private var name = ""
    @State private var phone = ""
    @State private var confirmDelete = false
    @State private var errorMessage: String?

    var body: some View {
        Form {
            Section("Profile") {
                TextField("Name", text: $name)
                TextField("Phone", text: $phone).keyboardType(.phonePad)
                Button("Save") {
                    Task {
                        do { try await session.update(name: name.nilIfEmpty, phone: phone.nilIfEmpty) }
                        catch { errorMessage = error.localizedDescription }
                    }
                }
            }
            Section {
                Button("Delete account", role: .destructive) { confirmDelete = true }
            } footer: {
                Text("This cancels active subscriptions and permanently deletes your shopper profile. Past store orders remain as business records without an account link.")
            }
            ErrorText(message: errorMessage)
        }
        .navigationTitle("Account settings")
        .onAppear { name = session.shopper?.name ?? ""; phone = session.shopper?.phone ?? "" }
        .confirmationDialog("Permanently delete your account?", isPresented: $confirmDelete, titleVisibility: .visible) {
            Button("Delete account", role: .destructive) {
                Task {
                    do { try await session.deleteAccount(); dismiss() }
                    catch { errorMessage = error.localizedDescription }
                }
            }
        }
    }
}

private struct BlogStrip: View {
    let posts: [BlogPost]
    var body: some View {
        VStack(alignment: .leading) {
            Text("From \(Config.current.displayName)").font(.title3.bold()).padding(.horizontal)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 12) {
                    ForEach(posts) { post in
                        VStack(alignment: .leading, spacing: 5) {
                            Text(post.title).font(.headline).lineLimit(2)
                            Text(post.excerpt ?? "").font(.caption).foregroundStyle(.secondary).lineLimit(3)
                        }
                        .frame(width: 220, alignment: .leading).padding()
                        .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 14))
                    }
                }
                .padding(.horizontal)
            }
        }
    }
}

private func optionalBinding(_ source: Binding<String?>) -> Binding<String> {
    Binding<String>(
        get: { source.wrappedValue ?? "" },
        set: { source.wrappedValue = $0.isEmpty ? nil : $0 }
    )
}

private extension String {
    var nilIfEmpty: String? {
        let value = trimmingCharacters(in: .whitespacesAndNewlines)
        return value.isEmpty ? nil : value
    }
}
