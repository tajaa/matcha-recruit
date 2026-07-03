#!/usr/bin/env ruby
# Idempotent helper to add Swift sources to Matcha.xcodeproj.
#
# Usage:
#   ./add_sources.rb <group_path> <file_relative_to_group> [<file2> ...]
#
# Example:
#   ./add_sources.rb Matcha/Models/MatchaWork ThreadModels.swift ProjectModels.swift
#
# - Creates intermediate PBXGroups if missing (resolved against the root project group).
# - Adds PBXFileReference + PBXBuildFile + Sources build phase entries.
# - Skips files already present.
# - Removes empty files from disk first if they're being re-added (safety: never).
#
# Requires the `xcodeproj` gem: `gem install xcodeproj`.

require "xcodeproj"
require "pathname"

PROJECT_PATH = File.expand_path("../Matcha.xcodeproj", __dir__)

def die(msg)
  warn "add_sources.rb: #{msg}"
  exit 1
end

die "usage: add_sources.rb <group_path> <file> [<file> ...]" if ARGV.size < 2

group_path = ARGV.shift
file_rel_paths = ARGV

project = Xcodeproj::Project.open(PROJECT_PATH)
main_target = project.targets.find { |t| t.name == "Matcha" } || die("Matcha target missing")

# Resolve / create the nested group chain (project root → group_path components).
group_components = group_path.split("/").reject(&:empty?)
# Walk/create the group chain manually so each newly-created group gets its
# `path` set to its filesystem folder name. `find_subpath(_, true)` would
# create groups without a `path` attribute, which makes `real_path` inherit
# from the parent — breaking the disk-path resolution below.
target_group = project.main_group
group_components.each do |name|
  child = target_group.children.find { |c| c.is_a?(Xcodeproj::Project::Object::PBXGroup) && (c.display_name == name || c.path == name) }
  unless child
    child = target_group.new_group(name, name)
  end
  child.set_source_tree("<group>")
  target_group = child
end

added_count = 0
skipped_count = 0

file_rel_paths.each do |file_rel|
  # Compute the on-disk path the new reference should point to.
  # PBXGroup with sourceTree=<group> means children are resolved relative
  # to the group's own path. The group's real_path gives us that.
  group_real_path = target_group.real_path
  file_disk_path = group_real_path.join(file_rel)
  unless file_disk_path.exist?
    die "file does not exist on disk: #{file_disk_path}"
  end

  # Skip if a reference for this filename already exists in the group.
  existing = target_group.files.find { |f| f.display_name == File.basename(file_rel) }
  if existing
    skipped_count += 1
    next
  end

  file_ref = target_group.new_reference(file_rel)
  file_ref.last_known_file_type = "sourcecode.swift"
  main_target.add_file_references([file_ref])
  added_count += 1
end

project.save
puts "added=#{added_count} skipped=#{skipped_count} group=#{group_path}"
