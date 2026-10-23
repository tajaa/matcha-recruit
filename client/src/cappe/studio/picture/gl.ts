// The Picture Editor's renderer: one WebGL2 program (develop.ts) over the
// source picture, drawing a recipe at any size. The same class draws the
// preview on screen and the full-size result that is uploaded. Originals are
// at most 3200 px (services/media.py), so one texture holds any of them.

import { FRAGMENT, VERTEX, hueRgb } from './develop'
import { WHOLE, coverScale, turned, type Crop, type Recipe } from './recipe'

export type Canvas = HTMLCanvasElement | OffscreenCanvas
export type Draw = {
  /** "Before": the picture as it was (cropped as the recipe says). */
  before?: boolean
  /** Show the whole frame (turned, flipped, straightened) without its crop: the crop tool's view. */
  uncropped?: boolean
  /** Leave the cut-out off (to show what's being cut away). */
  noMask?: boolean
}

const UNIFORMS = ['uSrc', 'uMask', 'uOut', 'uSrcSize', 'uCrop', 'uTurned', 'uAngle', 'uScale', 'uTurn', 'uFlip',
  'uAdjust', 'uExposure', 'uContrast', 'uHighlights', 'uShadows', 'uWhites', 'uBlacks', 'uTemp', 'uTint', 'uVibrance',
  'uSaturation', 'uClarity', 'uSharpen', 'uVignette', 'uGrain', 'uFade', 'uBw', 'uShAmt', 'uHiAmt', 'uShRgb', 'uHiRgb',
  'uMaskOn', 'uFeather', 'uInvert'] as const

export class PictureGL {
  readonly gl: WebGL2RenderingContext
  private program: WebGLProgram
  private loc = {} as Record<(typeof UNIFORMS)[number], WebGLUniformLocation | null>
  private src: WebGLTexture
  private mask: WebGLTexture
  private srcSize: [number, number] = [1, 1]
  private hasMask = false
  readonly canvas: Canvas

  constructor(canvas: Canvas) {
    this.canvas = canvas
    const gl = canvas.getContext('webgl2', { premultipliedAlpha: true, preserveDrawingBuffer: true, antialias: false })
    if (!gl) throw new Error('This browser can’t draw pictures with WebGL 2.')
    this.gl = gl as WebGL2RenderingContext
    this.program = this.link()
    for (const name of UNIFORMS) this.loc[name] = this.gl.getUniformLocation(this.program, name)
    this.src = this.texture()
    this.mask = this.texture()
    const buf = this.gl.createBuffer()
    this.gl.bindBuffer(this.gl.ARRAY_BUFFER, buf)
    this.gl.bufferData(this.gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), this.gl.STATIC_DRAW)
    const at = this.gl.getAttribLocation(this.program, 'aPos')
    this.gl.enableVertexAttribArray(at)
    this.gl.vertexAttribPointer(at, 2, this.gl.FLOAT, false, 0, 0)
  }

  private link(): WebGLProgram {
    const { gl } = this
    const shader = (type: number, source: string) => {
      const s = gl.createShader(type)!
      gl.shaderSource(s, source)
      gl.compileShader(s)
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s) || 'shader')
      return s
    }
    const p = gl.createProgram()!
    gl.attachShader(p, shader(gl.VERTEX_SHADER, VERTEX))
    gl.attachShader(p, shader(gl.FRAGMENT_SHADER, FRAGMENT))
    gl.linkProgram(p)
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p) || 'program')
    gl.useProgram(p)
    return p
  }

  private texture(): WebGLTexture {
    const { gl } = this
    const t = gl.createTexture()!
    gl.bindTexture(gl.TEXTURE_2D, t)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
    return t
  }

  /** The largest picture this device can hold in one texture. */
  get maxSize(): number {
    return this.gl.getParameter(this.gl.MAX_TEXTURE_SIZE) as number
  }

  setSource(image: ImageBitmap | HTMLImageElement | HTMLCanvasElement | OffscreenCanvas, width: number, height: number): void {
    const { gl } = this
    gl.activeTexture(gl.TEXTURE0)
    gl.bindTexture(gl.TEXTURE_2D, this.src)
    gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false)
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, image)
    gl.generateMipmap(gl.TEXTURE_2D)
    this.srcSize = [width, height]
  }

  /** The cut-out: one byte a source pixel (255 kept), or none. */
  setMask(alpha: Uint8Array | null, width = 0, height = 0): void {
    const { gl } = this
    this.hasMask = !!alpha
    if (!alpha) return
    gl.activeTexture(gl.TEXTURE1)
    gl.bindTexture(gl.TEXTURE_2D, this.mask)
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1)
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.R8, width, height, 0, gl.RED, gl.UNSIGNED_BYTE, alpha)
    gl.generateMipmap(gl.TEXTURE_2D)
  }

  /** Draw the recipe into the canvas at `width` × `height`. */
  draw(recipe: Recipe, width: number, height: number, opts: Draw = {}): void {
    const { gl, loc } = this
    if (this.canvas.width !== width) this.canvas.width = width
    if (this.canvas.height !== height) this.canvas.height = height
    gl.viewport(0, 0, width, height)
    gl.clearColor(0, 0, 0, 0)
    gl.clear(gl.COLOR_BUFFER_BIT)
    gl.useProgram(this.program)
    gl.activeTexture(gl.TEXTURE0)
    gl.bindTexture(gl.TEXTURE_2D, this.src)
    gl.activeTexture(gl.TEXTURE1)
    gl.bindTexture(gl.TEXTURE_2D, this.mask)
    gl.uniform1i(loc.uSrc, 0)
    gl.uniform1i(loc.uMask, 1)

    const [sw, sh] = this.srcSize
    const geo: Crop = recipe.crop ?? WHOLE
    const crop = opts.uncropped ? { ...geo, x: 0, y: 0, w: 1, h: 1 } : geo
    const [tw, th] = turned(sw, sh, crop.turn)
    gl.uniform2f(loc.uOut, width, height)
    gl.uniform2f(loc.uSrcSize, sw, sh)
    gl.uniform4f(loc.uCrop, crop.x, crop.y, crop.w, crop.h)
    gl.uniform2f(loc.uTurned, tw, th)
    gl.uniform1f(loc.uAngle, (crop.angle * Math.PI) / 180)
    gl.uniform1f(loc.uScale, coverScale(tw, th, crop.angle))
    gl.uniform1i(loc.uTurn, crop.turn)
    gl.uniform2f(loc.uFlip, crop.flip_h ? 1 : 0, crop.flip_v ? 1 : 0)

    const v = (k: keyof Recipe) => ((recipe[k] as number | undefined) ?? 0) / 100
    gl.uniform1f(loc.uAdjust, opts.before ? 0 : 1)
    gl.uniform1f(loc.uExposure, recipe.exposure ?? 0)
    gl.uniform1f(loc.uContrast, v('contrast'))
    gl.uniform1f(loc.uHighlights, v('highlights'))
    gl.uniform1f(loc.uShadows, v('shadows'))
    gl.uniform1f(loc.uWhites, v('whites'))
    gl.uniform1f(loc.uBlacks, v('blacks'))
    gl.uniform1f(loc.uTemp, v('temp'))
    gl.uniform1f(loc.uTint, v('tint'))
    gl.uniform1f(loc.uVibrance, v('vibrance'))
    gl.uniform1f(loc.uSaturation, v('saturation'))
    gl.uniform1f(loc.uClarity, v('clarity'))
    gl.uniform1f(loc.uSharpen, v('sharpen'))
    gl.uniform1f(loc.uVignette, v('vignette'))
    gl.uniform1f(loc.uGrain, v('grain'))
    gl.uniform1f(loc.uFade, v('fade'))
    gl.uniform1f(loc.uBw, recipe.bw ? 1 : 0)
    gl.uniform1f(loc.uShAmt, v('sh_amt'))
    gl.uniform1f(loc.uHiAmt, v('hi_amt'))
    gl.uniform3f(loc.uShRgb, ...hueRgb(recipe.sh_hue ?? 0))
    gl.uniform3f(loc.uHiRgb, ...hueRgb(recipe.hi_hue ?? 0))
    const cut = recipe.cutout
    gl.uniform1f(loc.uMaskOn, this.hasMask && cut && !opts.noMask && !opts.before ? 1 : 0)
    // Feather: how far down the mask's mipmaps to read (0 sharp … 4 soft).
    gl.uniform1f(loc.uFeather, ((cut?.feather ?? 0) / 100) * 4)
    gl.uniform1f(loc.uInvert, cut?.invert ? 1 : 0)
    gl.drawArrays(gl.TRIANGLES, 0, 3)
  }

  /** The canvas's pixels (top row first), RGBA: for tests and the likeness of a draw. */
  read(): Uint8Array {
    const { gl } = this
    const w = this.canvas.width, h = this.canvas.height
    const out = new Uint8Array(w * h * 4)
    gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, out)
    const row = w * 4, flipped = new Uint8Array(out.length)
    for (let y = 0; y < h; y++) flipped.set(out.subarray((h - 1 - y) * row, (h - y) * row), y * row)
    return flipped
  }

  dispose(): void {
    const { gl } = this
    gl.deleteTexture(this.src)
    gl.deleteTexture(this.mask)
    gl.deleteProgram(this.program)
    gl.getExtension('WEBGL_lose_context')?.loseContext()
  }
}
