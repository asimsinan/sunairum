/**
 * Port of ng-animated-login/src/assets/login-animation.js (GSAP TweenMax → gsap 3).
 * Same caret-tracking, mouth morph, and arm cover/uncover behavior.
 */
import gsap from 'gsap'

type BindOpts = {
  root: HTMLElement
  email: HTMLInputElement
  password: HTMLInputElement
}

export type LoginYetiApi = {
  coverEyes: () => void
  uncoverEyes: () => void
  destroy: () => void
}

function getAngle(x1: number, y1: number, x2: number, y2: number) {
  return Math.atan2(y1 - y2, x1 - x2)
}

function getPosition(el: HTMLElement | SVGElement | null) {
  let xPos = 0
  let yPos = 0
  let node: HTMLElement | SVGElement | null = el
  while (node) {
    const html = node as HTMLElement
    if (html.tagName === 'BODY') {
      const xScroll = html.scrollLeft || document.documentElement.scrollLeft
      const yScroll = html.scrollTop || document.documentElement.scrollTop
      xPos += html.offsetLeft - xScroll + html.clientLeft
      yPos += html.offsetTop - yScroll + html.clientTop
    } else if ('offsetLeft' in html) {
      xPos += html.offsetLeft - html.scrollLeft + html.clientLeft
      yPos += html.offsetTop - html.scrollTop + html.clientTop
    }
    node = html.offsetParent as HTMLElement | null
  }
  return { x: xPos, y: yPos }
}

function morphMouth(targets: Element[], source: SVGPathElement | null) {
  if (!source) return
  const d = source.getAttribute('d')
  if (!d) return
  // Smile / medium / large mouths use incompatible path command lists.
  // Tweening `attr.d` without MorphSVGPlugin interpolates into a long
  // horizontal stroke (black line across the face) on the first keystroke.
  gsap.killTweensOf(targets)
  gsap.set(targets, { attr: { d } })
}

export function bindLoginYetiAnimation({ root, email, password }: BindOpts): LoginYetiApi {
  const q = <T extends Element>(sel: string) => root.querySelector(sel) as T | null

  // root is the .svgContainer element (same as original query).
  const mySVG = root
  const armL = q<SVGGElement>('.armL')
  const armR = q<SVGGElement>('.armR')
  const eyeL = q<SVGGElement>('.eyeL')
  const eyeR = q<SVGGElement>('.eyeR')
  const nose = q<SVGPathElement>('.nose')
  const mouth = q<SVGGElement>('.mouth')
  const mouthBG = q<SVGPathElement>('.mouthBG')
  const mouthSmallBG = q<SVGPathElement>('.mouthSmallBG')
  const mouthMediumBG = q<SVGPathElement>('.mouthMediumBG')
  const mouthLargeBG = q<SVGPathElement>('.mouthLargeBG')
  const mouthMaskPath = q<SVGPathElement>('.mouthMaskPath')
  const mouthOutline = q<SVGPathElement>('.mouthOutline')
  const tooth = q<SVGPathElement>('.tooth')
  const tongue = q<SVGGElement>('.tongue')
  const chin = q<SVGPathElement>('.chin')
  const face = q<SVGPathElement>('.face')
  const eyebrow = q<SVGGElement>('.eyebrow')
  const outerEarL = q<SVGGElement>('.earL .outerEar')
  const outerEarR = q<SVGGElement>('.earR .outerEar')
  const earHairL = q<SVGGElement>('.earL .earHair')
  const earHairR = q<SVGGElement>('.earR .earHair')
  const hair = q<SVGPathElement>('.hair')

  const eyeMaxHorizD = 20
  const eyeMaxVertD = 10
  const noseMaxHorizD = 23
  const noseMaxVertD = 10
  let mouthStatus: 'small' | 'medium' | 'large' = 'small'
  let reduced =
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches

  const mouthMorphTargets = () =>
    [mouthBG, mouthOutline, mouthMaskPath].filter(Boolean) as Element[]

  function getCoord() {
    if (reduced || !eyeL || !eyeR || !nose || !mouth) return

    const carPos = email.selectionEnd ?? email.value.length
    const div = document.createElement('div')
    const span = document.createElement('span')
    const copyStyle = getComputedStyle(email)
    for (let i = 0; i < copyStyle.length; i++) {
      const prop = copyStyle.item(i)
      if (prop) div.style.setProperty(prop, copyStyle.getPropertyValue(prop))
    }
    div.style.position = 'absolute'
    div.style.visibility = 'hidden'
    div.style.whiteSpace = 'pre-wrap'
    document.body.appendChild(div)
    div.textContent = email.value.substring(0, carPos)
    span.textContent = email.value.substring(carPos) || '.'
    div.appendChild(span)

    const emailCoords = getPosition(email)
    const caretCoords = getPosition(span)
    const svgCoords = getPosition(mySVG)
    const screenCenter = svgCoords.x + mySVG.offsetWidth / 2
    const caretPos = caretCoords.x + emailCoords.x
    const dFromC = screenCenter - caretPos

    let eyeDistH = -dFromC * 0.05
    if (eyeDistH > eyeMaxHorizD) eyeDistH = eyeMaxHorizD
    else if (eyeDistH < -eyeMaxHorizD) eyeDistH = -eyeMaxHorizD

    const eyeLCoords = { x: svgCoords.x + 84, y: svgCoords.y + 76 }
    const eyeRCoords = { x: svgCoords.x + 113, y: svgCoords.y + 76 }
    const noseCoords = { x: svgCoords.x + 97, y: svgCoords.y + 81 }
    const mouthCoords = { x: svgCoords.x + 100, y: svgCoords.y + 100 }
    const targetX = emailCoords.x + caretCoords.x
    const targetY = emailCoords.y + 25

    const eyeLAngle = getAngle(eyeLCoords.x, eyeLCoords.y, targetX, targetY)
    const eyeLX = Math.cos(eyeLAngle) * eyeMaxHorizD
    const eyeLY = Math.sin(eyeLAngle) * eyeMaxVertD
    const eyeRAngle = getAngle(eyeRCoords.x, eyeRCoords.y, targetX, targetY)
    const eyeRX = Math.cos(eyeRAngle) * eyeMaxHorizD
    const eyeRY = Math.sin(eyeRAngle) * eyeMaxVertD
    const noseAngle = getAngle(noseCoords.x, noseCoords.y, targetX, targetY)
    const noseX = Math.cos(noseAngle) * noseMaxHorizD
    const noseY = Math.sin(noseAngle) * noseMaxVertD
    const mouthAngle = getAngle(mouthCoords.x, mouthCoords.y, targetX, targetY)
    const mouthX = Math.cos(mouthAngle) * noseMaxHorizD
    const mouthY = Math.sin(mouthAngle) * noseMaxVertD
    const mouthR = Math.cos(mouthAngle) * 6
    const chinX = mouthX * 0.8
    const chinY = mouthY * 0.5
    let chinS = 1 - (dFromC * 0.15) / 100
    if (chinS > 1) chinS = 1 - (chinS - 1)
    const faceX = mouthX * 0.3
    const faceY = mouthY * 0.4
    const faceSkew = Math.cos(mouthAngle) * 5
    const eyebrowSkew = Math.cos(mouthAngle) * 25
    const outerEarX = Math.cos(mouthAngle) * 4
    const outerEarY = Math.cos(mouthAngle) * 5
    const hairX = Math.cos(mouthAngle) * 6
    const hairS = 1.2

    gsap.to(eyeL, { duration: 1, x: -eyeLX, y: -eyeLY, ease: 'expo.out' })
    gsap.to(eyeR, { duration: 1, x: -eyeRX, y: -eyeRY, ease: 'expo.out' })
    gsap.to(nose, {
      duration: 1,
      x: -noseX,
      y: -noseY,
      rotation: mouthR,
      transformOrigin: 'center center',
      ease: 'expo.out',
    })
    gsap.to(mouth, {
      duration: 1,
      x: -mouthX,
      y: -mouthY,
      rotation: mouthR,
      transformOrigin: 'center center',
      ease: 'expo.out',
    })
    if (chin) gsap.to(chin, { duration: 1, x: -chinX, y: -chinY, scaleY: chinS, ease: 'expo.out' })
    if (face)
      gsap.to(face, {
        duration: 1,
        x: -faceX,
        y: -faceY,
        skewX: -faceSkew,
        transformOrigin: 'center top',
        ease: 'expo.out',
      })
    if (eyebrow)
      gsap.to(eyebrow, {
        duration: 1,
        x: -faceX,
        y: -faceY,
        skewX: -eyebrowSkew,
        transformOrigin: 'center top',
        ease: 'expo.out',
      })
    if (outerEarL) gsap.to(outerEarL, { duration: 1, x: outerEarX, y: -outerEarY, ease: 'expo.out' })
    if (outerEarR) gsap.to(outerEarR, { duration: 1, x: outerEarX, y: outerEarY, ease: 'expo.out' })
    if (earHairL) gsap.to(earHairL, { duration: 1, x: -outerEarX, y: -outerEarY, ease: 'expo.out' })
    if (earHairR) gsap.to(earHairR, { duration: 1, x: -outerEarX, y: outerEarY, ease: 'expo.out' })
    if (hair)
      gsap.to(hair, {
        duration: 1,
        x: hairX,
        scaleY: hairS,
        transformOrigin: 'center bottom',
        ease: 'expo.out',
      })

    document.body.removeChild(div)
  }

  function onEmailInput() {
    getCoord()
    const value = email.value
    const curEmailIndex = value.length
    if (reduced) return

    if (curEmailIndex > 0) {
      if (value.includes('@')) {
        if (mouthStatus === 'large') return
        mouthStatus = 'large'
        morphMouth(mouthMorphTargets(), mouthLargeBG)
        if (tooth) gsap.to(tooth, { duration: 1, x: 3, y: -2, ease: 'expo.out' })
        if (tongue) gsap.to(tongue, { duration: 1, y: 2, ease: 'expo.out' })
        gsap.to([eyeL, eyeR], {
          duration: 1,
          scaleX: 0.65,
          scaleY: 0.65,
          ease: 'expo.out',
          transformOrigin: 'center center',
        })
      } else {
        if (mouthStatus === 'medium') return
        mouthStatus = 'medium'
        morphMouth(mouthMorphTargets(), mouthMediumBG)
        if (tooth) gsap.to(tooth, { duration: 1, x: 0, y: 0, ease: 'expo.out' })
        if (tongue) gsap.to(tongue, { duration: 1, x: 0, y: 1, ease: 'expo.out' })
        gsap.to([eyeL, eyeR], { duration: 1, scaleX: 0.85, scaleY: 0.85, ease: 'expo.out' })
      }
    } else if (mouthStatus !== 'small') {
      mouthStatus = 'small'
      morphMouth(mouthMorphTargets(), mouthSmallBG)
      if (tooth) gsap.to(tooth, { duration: 1, x: 0, y: 0, ease: 'expo.out' })
      if (tongue) gsap.to(tongue, { duration: 1, y: 0, ease: 'expo.out' })
      gsap.to([eyeL, eyeR], { duration: 1, scaleX: 1, scaleY: 1, ease: 'expo.out' })
    }
  }

  function onEmailFocus() {
    email.parentElement?.classList.add('focusWithText')
    getCoord()
  }

  function onEmailBlur() {
    if (email.value === '') email.parentElement?.classList.remove('focusWithText')
    resetFace()
  }

  function coverEyes() {
    if (!armL || !armR) return
    gsap.to(armL, { duration: 0.45, x: -93, y: 2, rotation: 0, ease: 'power2.out' })
    gsap.to(armR, { duration: 0.45, x: -93, y: 2, rotation: 0, ease: 'power2.out', delay: 0.1 })
  }

  function uncoverEyes() {
    if (!armL || !armR) return
    gsap.to(armL, { duration: 1.35, y: 220, ease: 'power2.out' })
    gsap.to(armL, { duration: 1.35, rotation: 105, ease: 'power2.out', delay: 0.1 })
    gsap.to(armR, { duration: 1.35, y: 220, ease: 'power2.out' })
    gsap.to(armR, { duration: 1.35, rotation: -105, ease: 'power2.out', delay: 0.1 })
  }

  function resetFace() {
    if (reduced) return
    gsap.to([eyeL, eyeR], { duration: 1, x: 0, y: 0, ease: 'expo.out' })
    if (nose) gsap.to(nose, { duration: 1, x: 0, y: 0, scaleX: 1, scaleY: 1, ease: 'expo.out' })
    if (mouth) gsap.to(mouth, { duration: 1, x: 0, y: 0, rotation: 0, ease: 'expo.out' })
    if (chin) gsap.to(chin, { duration: 1, x: 0, y: 0, scaleY: 1, ease: 'expo.out' })
    gsap.to([face, eyebrow], { duration: 1, x: 0, y: 0, skewX: 0, ease: 'expo.out' })
    gsap.to([outerEarL, outerEarR, earHairL, earHairR, hair], {
      duration: 1,
      x: 0,
      y: 0,
      scaleY: 1,
      ease: 'expo.out',
    })
  }

  function onPasswordFocus() {
    coverEyes()
  }

  function onPasswordBlur() {
    uncoverEyes()
  }

  email.addEventListener('focus', onEmailFocus)
  email.addEventListener('blur', onEmailBlur)
  email.addEventListener('input', onEmailInput)
  password.addEventListener('focus', onPasswordFocus)
  password.addEventListener('blur', onPasswordBlur)

  if (armL) gsap.set(armL, { x: -93, y: 220, rotation: 105, transformOrigin: 'top left' })
  if (armR) gsap.set(armR, { x: -93, y: 220, rotation: -105, transformOrigin: 'top right' })

  return {
    coverEyes,
    uncoverEyes,
    destroy() {
      email.removeEventListener('focus', onEmailFocus)
      email.removeEventListener('blur', onEmailBlur)
      email.removeEventListener('input', onEmailInput)
      password.removeEventListener('focus', onPasswordFocus)
      password.removeEventListener('blur', onPasswordBlur)
      gsap.killTweensOf([
        armL,
        armR,
        eyeL,
        eyeR,
        nose,
        mouth,
        chin,
        face,
        eyebrow,
        outerEarL,
        outerEarR,
        earHairL,
        earHairR,
        hair,
        tooth,
        tongue,
        mouthBG,
        mouthOutline,
        mouthMaskPath,
      ])
    },
  }
}
