import { BODY_WRITING_NOTICE } from '../writing'
import { ui } from './state'

let notice: HTMLElement | undefined
let timer: ReturnType<typeof setTimeout> | undefined

export function writingNotice(): void {
  if (!notice?.isConnected) {
    notice = ui('div', 'mze-writing')
    notice.setAttribute('role', 'status')
  }
  clearTimeout(timer)
  notice.textContent = BODY_WRITING_NOTICE
  notice.hidden = false
  timer = setTimeout(() => { if (notice) notice.hidden = true }, 5000)
}
