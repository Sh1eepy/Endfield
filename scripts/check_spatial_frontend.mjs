// Local browser evidence. Uses an existing Playwright installation; installs nothing.
// node scripts/check_spatial_frontend.mjs <path-to-playwright> [output-directory]
import { createRequire } from 'node:module'
import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
const require = createRequire(import.meta.url)
const { chromium } = require(process.argv[2] || 'playwright')
const out = path.resolve(process.argv[3] || 'output/frontend-spatial')
await mkdir(out, {recursive:true})
const browser = await chromium.launch({headless:true,channel:'msedge'})
const report = []
try {
  for (const size of [{width:1440,height:900},{width:390,height:844}]) {
    const page = await browser.newPage({viewport:size,deviceScaleFactor:1,hasTouch:size.width===390})
    const errors=[]
    page.on('pageerror', e=>errors.push(e.message))
    await page.goto('http://127.0.0.1:5173', {waitUntil:'networkidle'})
    await page.waitForTimeout(7000)
    await page.screenshot({path:path.join(out,`home-${size.width}.png`)})
    const homeYaw=await page.locator('.experience-scene').getAttribute('data-yaw')
    if(size.width===1440) {
      await page.evaluate(()=>window.dispatchEvent(new Event('endfield-replay-entry')))
      await page.waitForTimeout(800)
      await page.screenshot({path:path.join(out,'entry-access.png')})
      await page.waitForTimeout(1500)
      await page.screenshot({path:path.join(out,'entry-scan.png')})
      await page.waitForTimeout(1900)
      await page.screenshot({path:path.join(out,'entry-welcome.png')})
      await page.waitForTimeout(2400)
    }
    await page.locator('.archive-bridge').evaluate(el=>window.scrollTo({top:el.getBoundingClientRect().top+window.scrollY-innerHeight/2,behavior:'instant'}))
    await page.waitForTimeout(700)
    await page.screenshot({path:path.join(out,`bridge-${size.width}.png`)})
    await page.locator('.archive-query').evaluate(el=>window.scrollTo({top:el.getBoundingClientRect().top+window.scrollY,behavior:'instant'}))
    await page.waitForTimeout(1600)
    await page.screenshot({path:path.join(out,`query-${size.width}.png`)})
    report.push({size,homeYaw,queryYaw:await page.locator('.experience-scene').getAttribute('data-yaw')})
    if(size.width===390)await page.locator('[data-mode="ask"]').tap()
    else await page.locator('[data-mode="ask"]').click()
    await page.waitForTimeout(1300)
    if(size.width>600)await page.mouse.move(size.width*.8,size.height*.3)
    await page.waitForTimeout(900)
    await page.screenshot({path:path.join(out,`orbit-right-${size.width}.png`)})
    if(size.width>600)await page.mouse.move(size.width*.15,size.height*.4)
    await page.waitForTimeout(900)
    await page.screenshot({path:path.join(out,`orbit-left-${size.width}.png`)})
    if(size.width===1440) {
      const initial=await page.locator('.experience-scene').getAttribute('data-selected')
      let changed=false
      for(const x of [.7,.8,.9]) {
        for(const y of [.18,.26,.48]) {
          const point={x:size.width*x,y:size.height*y}
          if(!await page.evaluate(p=>document.elementFromPoint(p.x,p.y)?.classList.contains('helix-hitarea'),point))continue
          await page.mouse.click(point.x,point.y)
          await page.waitForTimeout(150)
          changed=initial!==await page.locator('.experience-scene').getAttribute('data-selected')
          if(changed)break
        }
        if(changed)break
      }
      report.push({desktopPointerPickChangedSelection:changed})
      await page.screenshot({path:path.join(out,'picked-outline-1440.png')})
    }
    // Browser-only response fixture; no paid model call or production data mutation.
    await page.route('**/api/ask/stream',async route=>{
      await new Promise(resolve=>setTimeout(resolve,2200))
      await route.fulfill({status:200,contentType:'text/event-stream',body:'event: phase\ndata: {"text":"浏览器验证：正在检索"}\n\nevent: delta\ndata: {"text":"这是浏览器动效验证内容，不是知识库回答。"}\n\nevent: done\ndata: {"ok":true,"answer":"这是浏览器动效验证内容，不是知识库回答。"}\n\n'})
    })
    await page.locator('#in-search').fill('前端动效验证')
    await page.locator('#in-search').press('Enter')
    await page.waitForTimeout(300)
    const progress=await page.locator('[role="progressbar"]').count()
    await page.screenshot({path:path.join(out,`waiting-${size.width}.png`)})
    await page.waitForTimeout(4300)
    await page.screenshot({path:path.join(out,`extracted-${size.width}.png`)})
    const opened=await page.locator('.experience-scene').getAttribute('data-extraction')
    report.push({size,readyHintAbsent:!await page.locator('.archive-status').innerText().then(t=>t.includes('档案内容已就绪')),skipHidden:!await page.locator('.archive-skip-extract').isVisible()})
    const framesBefore=await page.locator('.experience-scene').getAttribute('data-frames')
    await page.waitForTimeout(600)
    const readingPaused=framesBefore===await page.locator('.experience-scene').getAttribute('data-frames')
    if(size.width===390)await page.locator('.archive-detail-bar button').tap()
    else await page.locator('.archive-detail-bar button').click()
    await page.waitForTimeout(2200)
    const closed=await page.locator('.experience-scene').getAttribute('data-extraction')
    await page.screenshot({path:path.join(out,`returned-${size.width}.png`)})
    // Exercise the exact renderer with deterministic frames, inspecting world-space geometry.
    const geometry=await page.evaluate(async()=>{
      const {createArchiveScene}=await import('/src/scene/archiveScene.ts')
      const host=document.createElement('div');host.style.cssText='position:fixed;inset:0;z-index:9999';document.body.append(host)
      const scene=createArchiveScene(host,()=>{})
      const f={position:1,velocity:0,energy:0,pointerX:0,pointerY:0,time:1,extraction:0,browse:0}
      const cases=[]
      for(const pointerX of [-1,0,1]) {
        scene.render({...f,pointerX})
        const before=scene.inspect()
        let hits=0
        for(const [index,v] of before.projected.entries())if(Math.abs(v[0])<.85 && Math.abs(v[1])<.75 && scene.pick(v[0],v[1])===index+1)hits++
        scene.render({...f,pointerX,extraction:.01})
        const start=scene.inspect()
        scene.render({...f,pointerX,extraction:1})
        scene.render({...f,pointerX,extraction:.3})
        const returning=scene.inspect()
        scene.render({...f,pointerX,extraction:0})
        const end=scene.inspect()
        cases.push({pointerX,yaw:before.yaw,hits,ringFits:before.ringBounds.every(v=>Math.abs(v[0])<1 && Math.abs(v[1])<1),startError:start.originError,returnError:returning.originError,restored:end.visibleCarriers===56,poseError:Math.max(...before.origins.flatMap((v,i)=>v.map((n,j)=>Math.abs(n-end.origins[i][j]))))})
      }
      scene.dispose();host.remove();return cases
    })
    report.push({size,progress,opened,closed,readingPaused,geometry})
    report.push({size,errors,canvas:await page.locator('canvas').count(),layout:await page.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,chapter:getComputedStyle(document.querySelector('.archive-experience')).getPropertyValue('--chapter'),scene:document.querySelector('.experience-scene')?.getBoundingClientRect().toJSON()}))})
    if(size.width===390) {
      const before=await page.locator('.archive-experience').evaluate(el=>getComputedStyle(el).getPropertyValue('--world-x'))
      await page.locator('.archive-experience').dispatchEvent('pointermove',{pointerType:'touch',clientX:370,clientY:150})
      await page.waitForTimeout(400)
      report.push({touchPointerBefore:before,touchPointerX:await page.locator('.archive-experience').evaluate(el=>getComputedStyle(el).getPropertyValue('--world-x')),touchAction:await page.locator('.helix-hitarea').evaluate(el=>getComputedStyle(el).touchAction)})
    }
    await page.locator('canvas').evaluate(el=>el.getContext('webgl2')?.getExtension('WEBGL_lose_context')?.loseContext())
    await page.waitForTimeout(400)
    report.push({size,contextLossCanvasRemoved:await page.locator('canvas').count()===0})
    await page.screenshot({path:path.join(out,`fallback-${size.width}.png`)})
    await page.emulateMedia({reducedMotion:'reduce'})
    report.push({size,reducedCanvas:await page.locator('canvas').count()})
    await page.close()
  }
} finally {await browser.close()}
await writeFile(path.join(out,'report.json'),JSON.stringify(report,null,2))
console.log(JSON.stringify(report,null,2))
if(report.some(r=>r.geometry && (r.progress!==1 || r.opened!=='1.000' || r.closed!=='0.000' || !r.readingPaused || r.geometry.some(g=>!g.ringFits || !g.restored || g.hits<1 || g.startError>1e-6 || g.returnError>1e-6 || g.poseError>1e-6))))process.exitCode=1
