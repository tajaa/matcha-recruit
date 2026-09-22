#!/usr/bin/env ruby
# Adds a native iOS app target "WerkiOS" to Matcha.xcodeproj.
#
# - Shares the portable core (Models/Services/ViewModels) with the macOS
#   "Matcha" target via dual target membership (adds the existing file refs to
#   the iOS target's Sources build phase).
# - Mirrors the macOS target's Swift Package product dependencies (LiveKit etc.)
#   onto the iOS target so `import LiveKit` links.
# - iOS-only sources live under WerkiOS/.
#
# Idempotent: preserve target identity, signing settings, versions and schemes.
require 'xcodeproj'

project_path = File.expand_path('../Matcha.xcodeproj', __dir__)
srcroot      = File.expand_path('..', __dir__)
puts "ruby #{RUBY_VERSION} · xcodeproj #{Xcodeproj::VERSION}"
project = Xcodeproj::Project.open(project_path)

IOS_TARGET_NAME = 'WerkiOS'
BUNDLE_ID       = 'com.matchawork.app'
DEPLOY          = '17.0'

mac_target = project.targets.find { |t| t.name == 'Matcha' }
raise 'macOS target "Matcha" not found' unless mac_target

# Mirror the macOS Swift version so the shared core compiles identically.
swift_version = mac_target.build_configurations.first.build_settings['SWIFT_VERSION'] || '5.0'

# --- clean re-run -----------------------------------------------------------
existing = project.targets.find { |t| t.name == IOS_TARGET_NAME }

# --- create the iOS target --------------------------------------------------
ios = existing || project.new_target(:application, IOS_TARGET_NAME, :ios, DEPLOY)

# Shared files to add to the iOS target (matched by basename among existing
# project file references — all basenames are unique in this project).
shared_basenames = %w[
  ChannelModels.swift AuthModels.swift CallModels.swift BroadcastModels.swift
  InboxModels.swift BillingUsageModels.swift
  APIClient.swift AuthService.swift KeychainHelper.swift ChannelsService.swift
  InboxService.swift ChannelsWebSocket.swift CallService.swift
  BroadcastService.swift WorkDetailVMStore.swift
  ServiceCache.swift MultipartUploadBuilder.swift SafeURL.swift UsageBeaconService.swift MWLog.swift
  ChannelChatViewModel.swift
  CommonModels.swift DashboardModels.swift ProjectModels.swift ProjectTaskModels.swift
  ProjectBizModels.swift ProjectElementModels.swift ReplayModels.swift ThreadModels.swift
  JournalModels.swift WorkNotifications.swift
  MatchaWorkService.swift MatchaWorkService+Projects.swift MatchaWorkService+Tasks.swift
  MatchaWorkService+Files.swift MatchaWorkService+Collaborators.swift MatchaWorkService+Threads.swift
  MatchaWorkService+Elements.swift JournalService.swift ProjectWebSocket.swift TicketUpdatesStore.swift
  ProjectDetailViewModel.swift ProjectDetailViewModel+Core.swift ProjectDetailViewModel+Tasks.swift
  ProjectDetailViewModel+Files.swift ProjectDetailViewModel+Elements.swift ProjectPresenceViewModel.swift
  ThreadDetailViewModel.swift ThreadListViewModel.swift
  KanbanColumns.swift KanbanSearch.swift KanbanReplay.swift TaskProgressBar.swift
  TaskHistoryTimeline.swift MarkdownPreviewView.swift PresencePillContent.swift WorkToastCenter.swift
]

all_files = project.files
shared_refs = shared_basenames.map do |bn|
  ref = all_files.find { |f| f.path && File.basename(f.path) == bn }
  raise "shared file ref not found: #{bn}" unless ref
  ref
end
shared_refs.each { |ref| ios.source_build_phase.add_file_reference(ref, true) }
puts "Added #{shared_refs.size} shared source files to #{IOS_TARGET_NAME}"

# iOS-only sources group + files
# Recursively mirror the WerkiOS/ directory tree into the project: every .swift
# becomes a compiled source on the iOS target; Info.plist / entitlements are
# referenced (not compiled). Re-running the script picks up newly added files,
# so there's no per-file pbxproj surgery as the iOS surface grows.
def add_tree(project, parent_group, fs_path, rel_name, target)
  group = parent_group.groups.find { |item| item.path == rel_name } || parent_group.new_group(rel_name, rel_name)
  added = 0
  Dir.children(fs_path).sort.each do |entry|
    full = File.join(fs_path, entry)
    next if entry.start_with?('.')
    if entry.end_with?('.xcassets')
      ref = group.files.find { |item| item.path == entry } || group.new_reference(entry)
      target.resources_build_phase.add_file_reference(ref, true)
    elsif File.directory?(full)
      added += add_tree(project, group, full, entry, target)
    elsif entry.end_with?('.swift')
      ref = group.files.find { |item| item.path == entry } || group.new_reference(entry)
      target.source_build_phase.add_file_reference(ref, true)
      added += 1
    elsif entry == 'Info.plist' || entry.end_with?('.entitlements')
      group.new_reference(entry) unless group.files.any? { |item| item.path == entry }
    end
  end
  added
end

ios_count = add_tree(project, project.main_group, File.join(srcroot, IOS_TARGET_NAME), IOS_TARGET_NAME, ios)
puts "Added #{ios_count} iOS-only Swift files from #{IOS_TARGET_NAME}/"

# --- mirror Swift Package product dependencies (LiveKit, WebRTC, …) ----------
mirrored = []
mac_target.package_product_dependencies.each do |dep|
  next if ios.package_product_dependencies.any? { |item| item.product_name == dep.product_name }
  new_dep = project.new(Xcodeproj::Project::Object::XCSwiftPackageProductDependency)
  new_dep.package = dep.package if dep.package
  new_dep.product_name = dep.product_name
  ios.package_product_dependencies << new_dep

  bf = project.new(Xcodeproj::Project::Object::PBXBuildFile)
  bf.product_ref = new_dep
  ios.frameworks_build_phase.files << bf
  mirrored << dep.product_name
end
puts "Mirrored package products: #{mirrored.join(', ')}"

# --- build settings ---------------------------------------------------------
ios.build_configurations.each do |cfg|
  s = cfg.build_settings
  s['SDKROOT'] = 'iphoneos'
  s['IPHONEOS_DEPLOYMENT_TARGET'] = DEPLOY
  s['TARGETED_DEVICE_FAMILY'] = '1,2'
  s['PRODUCT_BUNDLE_IDENTIFIER'] = BUNDLE_ID
  s['PRODUCT_NAME'] = '$(TARGET_NAME)'
  s['GENERATE_INFOPLIST_FILE'] = 'NO'
  s['INFOPLIST_FILE'] = 'WerkiOS/Info.plist'
  s['CODE_SIGN_ENTITLEMENTS'] = 'WerkiOS/WerkiOS.entitlements'
  s['APS_ENVIRONMENT'] = cfg.name == 'Release' ? 'production' : 'development'
  s['ASSETCATALOG_COMPILER_APPICON_NAME'] = 'AppIcon'
  s['MARKETING_VERSION'] ||= '1.0'
  s['CURRENT_PROJECT_VERSION'] ||= '1'
  s['SWIFT_VERSION'] = swift_version
  s['CODE_SIGN_STYLE'] = 'Automatic'
  s['ENABLE_PREVIEWS'] = 'YES'
  s['SWIFT_EMIT_LOC_STRINGS'] = 'YES'
  s['LD_RUNPATH_SEARCH_PATHS'] = ['$(inherited)', '@executable_path/Frameworks']
  s['ASSETCATALOG_COMPILER_GENERATE_ASSET_SYMBOLS'] = 'NO'
  # Simulator builds don't need signing; keep device debug flexible.
  s['CODE_SIGN_IDENTITY[sdk=iphoneos*]'] = 'Apple Development'
end

project.save
puts "Saved. Targets now: #{project.targets.map(&:name).join(', ')}"

# --- shared scheme so `xcodebuild -scheme WerkiOS` works --------------------
scheme_path = File.join(project_path, 'xcshareddata', 'xcschemes', "#{IOS_TARGET_NAME}.xcscheme")
unless existing && File.exist?(scheme_path)
  scheme = Xcodeproj::XCScheme.new
  scheme.add_build_target(ios)
  scheme.set_launch_target(ios)
  scheme.save_as(project_path, IOS_TARGET_NAME, true)
end
puts "Wrote shared scheme #{IOS_TARGET_NAME}"
