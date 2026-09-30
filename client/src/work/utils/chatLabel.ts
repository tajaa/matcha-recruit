// A chat nobody named is titled "New Chat <date>" by the server. Lists
// already show when a chat happened, so the date in the title is noise:
// show "Untitled chat" and keep the real title for the tooltip.
const AUTO_TITLE = /^New Chat(?:\s+[A-Z][a-z]{2}\s+\d{1,2},\s+\d{4}.*)?$/

export function chatLabel(title: string): string {
  return AUTO_TITLE.test(title.trim()) ? 'Untitled chat' : title
}
