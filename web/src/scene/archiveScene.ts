import * as THREE from 'three'
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js'
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js'
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js'
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js'
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js'
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js'
import type { TransitionFrame } from './transition'
import { ARCHIVE_FACE, helixPoint } from './archiveGeometry'

export interface ArchiveScene {
  render(frame: TransitionFrame, chapter?: number): void
  pick(x: number,y: number): number | null
  inspect(): { selected:number; yaw:number; pitch:number; origins:number[][]; projected:number[][]; ringBounds:number[][]; extraction:number; originError:number|null; visibleCarriers:number; frames:number }
  dispose(): void
}
const smooth = (x: number) => { const t=Math.max(0,Math.min(1,x)); return t*t*(3-2*t) }
/** Spatial archive carriers, deliberately not bound to recipe or knowledge records. */
export function createArchiveScene(host: HTMLElement, onLost: () => void, onSelected?: (index:number)=>void): ArchiveScene {
  const renderer = new THREE.WebGLRenderer({ alpha:true,antialias:true,powerPreference:'high-performance' })
  renderer.toneMapping=THREE.ACESFilmicToneMapping
  renderer.toneMappingExposure=.88
  const world=new THREE.Scene()
  const camera=new THREE.PerspectiveCamera(36,1,.1,160)
  const room=new RoomEnvironment()
  const pmrem=new THREE.PMREMGenerator(renderer)
  const environment=pmrem.fromScene(room,.03)
  world.environment=environment.texture
  room.dispose();pmrem.dispose()
  world.add(new THREE.HemisphereLight(0xffffff,0x555d59,1.5))
  const key=new THREE.DirectionalLight(0xffffff,3.5);key.position.set(-8,12,18);world.add(key)
  const rim=new THREE.PointLight(0xf4ff74,70,35);rim.position.set(8,4,0);world.add(rim)
  const metal=new THREE.MeshStandardMaterial({color:0x505457,metalness:.88,roughness:.28})
  const porcelain=new THREE.MeshStandardMaterial({color:0xd7d8d1,metalness:.32,roughness:.3})
  const dark=new THREE.MeshStandardMaterial({color:0x202326,metalness:.55,roughness:.3})
  const yellow=new THREE.MeshStandardMaterial({color:0xf1f51d,emissive:0xe6ee17,emissiveIntensity:.48,roughness:.22,metalness:.35})
  const glass=new THREE.MeshPhysicalMaterial({color:0xe6e8e3,transmission:.94,thickness:.22,roughness:.12,ior:1.46,clearcoat:1,envMapIntensity:.85})
  const etched=new THREE.MeshStandardMaterial({color:0xcbd9d1,transparent:true,opacity:.26,metalness:.7,roughness:.2,depthWrite:false})
  const geometries:THREE.BufferGeometry[]=[]
  const shapes=new Map<string,THREE.BufferGeometry>()
  const box=(parent:THREE.Object3D,size:[number,number,number],at:[number,number,number],mat:THREE.Material) => {
    const id=size.join(',')
    if(!shapes.has(id)) { const g=new RoundedBoxGeometry(...size,5,Math.min(.07,Math.min(...size)/3));shapes.set(id,g);geometries.push(g) }
    const mesh=new THREE.Mesh(shapes.get(id),mat);mesh.position.set(...at);parent.add(mesh);return mesh
  }
  const prototype=new THREE.Group()
  box(prototype,[ARCHIVE_FACE.width,ARCHIVE_FACE.height,ARCHIVE_FACE.depth],[0,0,0],glass)
  box(prototype,[2.87,1.27,.12],[0,0,-.09],dark)
  box(prototype,[2.59,.91,.035],[0,.06,.015],porcelain)
  box(prototype,[3.08,.055,.46],[0,.77,0],metal)
  box(prototype,[3.08,.055,.46],[0,-.77,0],metal)
  box(prototype,[.065,1.46,.45],[-1.55,0,0],porcelain)
  box(prototype,[.065,1.46,.45],[1.55,0,0],porcelain)
  box(prototype,[.12,.66,.08],[-.91,.05,.14],yellow)
  box(prototype,[.67,.035,.05],[-.38,.17,.14],metal)
  box(prototype,[.44,.035,.05],[-.49,.04,.14],metal)
  box(prototype,[.9,.04,.055],[.55,-.2,.14],yellow)
  box(prototype,[.5,.12,.06],[.68,.23,.14],etched)
  // Both ring and moving archive share one world-space center; layout offset lives above them.
  const spatialRoot=new THREE.Group();spatialRoot.position.set(4.5,0,0);world.add(spatialRoot)
  const helix=new THREE.Group();spatialRoot.add(helix)
  const rings=new THREE.Group();rings.rotation.set(.12,0,-.06);spatialRoot.add(rings)
  const ringMaterial=new THREE.MeshStandardMaterial({color:0x555a5d,metalness:.82,roughness:.3})
  const ringAccent=new THREE.MeshStandardMaterial({color:0xcbd11d,emissive:0xb1b915,emissiveIntensity:.16,metalness:.45,roughness:.35})
  const ringMeshes:THREE.Mesh[]=[]
  for(const [radius,tube,y,material] of [[6.4,.065,0,ringMaterial],[6.57,.022,.3,ringAccent],[6.24,.026,-.35,ringMaterial]] as const) {
    const g=new THREE.TorusGeometry(radius,tube,8,128);geometries.push(g)
    const ring=new THREE.Mesh(g,material);ring.rotation.x=Math.PI/2;ring.position.y=y;ring.userData.baseY=y;rings.add(ring);ringMeshes.push(ring)
  }
  for(let i=0;i<24;i++) {
    const marker=new THREE.Group(),a=i/24*Math.PI*2
    marker.position.set(Math.cos(a)*6.4,0,Math.sin(a)*6.4);marker.rotation.y=-a
    box(marker,[i%6===0?.4:.16,.05,.045],[0,.085,0],i%6===0?ringAccent:ringMaterial);rings.add(marker)
  }
  const carriers:THREE.Group[]=[]
  for(let row=0;row<28;row++) for(let strand=0;strand<2;strand++) {
    const carrier=prototype.clone();carrier.userData={row,strand,index:carriers.length}
    carrier.traverse(child=>{child.userData.carrier=carriers.length})
    carriers.push(carrier);helix.add(carrier)
  }
  // Continuous backbone curves turn the two columns into a true vertical double helix.
  const strandMaterial=new THREE.MeshStandardMaterial({color:0xa5afaa,metalness:.9,roughness:.22,transparent:true,opacity:.5})
  const strands:THREE.Line[]=[]
  for(let strand=0;strand<2;strand++) {
    const g=new THREE.BufferGeometry().setFromPoints(Array.from({length:221},(_,i)=>new THREE.Vector3(...helixPoint(-20+i/220*40,strand,0))))
    geometries.push(g);const mesh=new THREE.Line(g,new THREE.LineBasicMaterial({color:0x989c94,transparent:true,opacity:.48}));strands.push(mesh);helix.add(mesh)
  }
  const linksMaterial=new THREE.LineBasicMaterial({color:0x959f96,transparent:true,opacity:.28})
  const linkArray=new Float32Array(28*6)
  const linkGeometry=new THREE.BufferGeometry();linkGeometry.setAttribute('position',new THREE.BufferAttribute(linkArray,3));geometries.push(linkGeometry)
  const links=new THREE.LineSegments(linkGeometry,linksMaterial);helix.add(links)
  const extracted=prototype.clone();world.add(extracted);extracted.visible=false
  let selected=26
  const selectionOutline=new THREE.Box3Helper(new THREE.Box3(new THREE.Vector3(-1.63,-.83,-.25),new THREE.Vector3(1.63,.83,.25)),0xcbd919)
  ;(selectionOutline.material as THREE.LineBasicMaterial).transparent=true
  ;(selectionOutline.material as THREE.LineBasicMaterial).opacity=.55
  carriers[selected].add(selectionOutline)
  let lockedOrigin:THREE.Vector3|null=null
  let lockedRotation:THREE.Quaternion|null=null
  let lastExtraction=0
  let elapsed=0,lastTime=0,frames=0
  const raycaster=new THREE.Raycaster()
  // Renderer antialias does not multisample the composer's offscreen targets.
  const target=new THREE.WebGLRenderTarget(1,1,{type:THREE.HalfFloatType,samples:Math.min(4,renderer.capabilities.maxSamples)})
  const composer=new EffectComposer(renderer,target)
  composer.addPass(new RenderPass(world,camera))
  const bloom=new UnrealBloomPass(new THREE.Vector2(1,1),.08,.25,1.8);composer.addPass(bloom)
  const output=new OutputPass();composer.addPass(output)
  const lightFog=new THREE.Color(0xdaddd5),darkFog=new THREE.Color(0x25282c)
  world.background=lightFog.clone();world.fog=new THREE.FogExp2(lightFog,.017)
  host.append(renderer.domElement)
  let disposed=false
  const resize=()=>{
    const width=Math.max(1,host.clientWidth),height=Math.max(1,host.clientHeight)
    renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,1.6));renderer.setSize(width,height)
    composer.setPixelRatio(renderer.getPixelRatio());composer.setSize(width,height)
    camera.aspect=width/height;camera.updateProjectionMatrix()
  }
  const observer=new ResizeObserver(resize);observer.observe(host);resize()
  const lost=(event:Event)=>{event.preventDefault();onLost()};renderer.domElement.addEventListener('webglcontextlost',lost)
  const finishPosition=new THREE.Vector3(),origin=new THREE.Vector3(),lookAt=new THREE.Vector3()
  const finishRotation=new THREE.Quaternion()
  return {
    render(frame, chapter = 1) {
      if(disposed)return
      const p=frame.position*smooth(chapter),e=frame.extraction
      elapsed+=lastTime && e===0?Math.min(.05,frame.time-lastTime):0;lastTime=frame.time
      const travel=smooth(e/.78),unfold=smooth((e-.55)/.45)
      const narrow=camera.aspect<.85
      helix.rotation.set(frame.pointerY*.13,frame.pointerX*.58+(frame.scrollOrbit ?? 0)+frame.browse*.035,0)
      const orbit=frame.scrollOrbit ?? 0
      rings.position.set(frame.pointerX*.3+Math.sin(orbit)*.2,frame.pointerY*.2+Math.sin(orbit*.8)*.16,0)
      rings.rotation.set(.12+frame.pointerY*.09+Math.sin(orbit)*.045,frame.pointerX*.12,-.06+frame.pointerX*.07)
      ringMeshes.forEach((ring,i)=>{
        const phase=elapsed*(.43+i*.13)+i*.8
        ring.rotation.x=Math.PI/2+Math.sin(phase)*(.014+i*.006)
        ring.rotation.y=Math.cos(phase*.83)*(.012+i*.005)
        ring.position.y=ring.userData.baseY+Math.sin(phase)*(.045+i*.022)
      })
      camera.position.set(narrow?6:10-7*p,3-1.8*p,(narrow?42:26)-2*p+5*(1-chapter))
      lookAt.set(narrow?4.5:1.6,0,0);camera.lookAt(lookAt)
      camera.fov=(narrow?49:36)+frame.energy*4-e*2;camera.updateProjectionMatrix()
      // Browsing moves carriers vertically while each keeps its helical phase.
      const drift=frame.browse+elapsed*.085
      for(const carrier of carriers) {
        const row=carrier.userData.row as number,strand=carrier.userData.strand as number
        const y=(((row-13)*1.4+drift+19.6)%39.2+39.2)%39.2-19.6
        const angle=y*.34+strand*Math.PI
        carrier.position.set(...helixPoint(y,strand,elapsed))
        carrier.rotation.set(.065*Math.sin(y*.52-elapsed*.95),-angle+Math.PI/2,.035*Math.sin(y*.52-elapsed*.95))
        carrier.visible=!(carrier.userData.index===selected && e>.005)
        const offset=row*6+strand*3
        linkArray[offset]=carrier.position.x;linkArray[offset+1]=carrier.position.y;linkArray[offset+2]=carrier.position.z
      }
      linkGeometry.attributes.position.needsUpdate=true
      selectionOutline.visible=e<.02
      if(selectionOutline.parent!==carriers[selected])carriers[selected].add(selectionOutline)
      strands.forEach((mesh,strand)=>{
        const attr=mesh.geometry.attributes.position
        for(let i=0;i<attr.count;i++)attr.setXYZ(i,...helixPoint(-20+i/(attr.count-1)*40,strand,elapsed))
        attr.needsUpdate=true
      })
      // Capture the actual selected box's world pose before lifting it out of the strand.
      if(e>.001 && lastExtraction<=.001) {
        world.updateMatrixWorld(true)
        camera.updateMatrixWorld(true)
        const projection=carriers[selected].getWorldPosition(new THREE.Vector3()).project(camera)
        if(Math.abs(projection.x)>.9 || Math.abs(projection.y)>.8) {
          let best=Infinity
          carriers.forEach((carrier,index)=>{
            const projected=carrier.getWorldPosition(new THREE.Vector3()).project(camera)
            const score=Math.abs(projected.y)*2+Math.abs(projected.x-.35)
            if(Math.abs(projected.x)<.9 && Math.abs(projected.y)<.8 && score<best){best=score;selected=index}
          })
          onSelected?.(selected+1)
        }
        lockedOrigin=carriers[selected].getWorldPosition(new THREE.Vector3())
        lockedRotation=carriers[selected].getWorldQuaternion(new THREE.Quaternion())
      }
      // On return, rejoin the actual slot (including any settled browse/pointer motion).
      if(e<lastExtraction && lockedOrigin && lockedRotation) {
        carriers[selected].getWorldPosition(lockedOrigin)
        carriers[selected].getWorldQuaternion(lockedRotation)
      }
      carriers.forEach(carrier=>{carrier.visible=!(carrier.userData.index===selected && e>.001)})
      extracted.visible=e>.001
      if(extracted.visible && lockedOrigin && lockedRotation) {
        const detail=host.closest('.archive-experience')?.querySelector<HTMLElement>('.archive-detail')
        const viewport=host.getBoundingClientRect()
        const parent=detail?.offsetParent?.getBoundingClientRect()
        const visibleHeight=2*Math.tan(THREE.MathUtils.degToRad(camera.fov/2))*12
        const visibleWidth=visibleHeight*camera.aspect
        let scaleX=narrow?2.55:4.35,scaleY=4.7
        if(detail && parent) {
          const centerX=parent.left+detail.offsetLeft+detail.offsetWidth/2
          const centerY=parent.top+detail.offsetTop+detail.offsetHeight/2
          finishPosition.set(((centerX-viewport.left)/viewport.width-.5)*visibleWidth,(.5-(centerY-viewport.top)/viewport.height)*visibleHeight,-12)
          scaleX=detail.offsetWidth/viewport.width*visibleWidth/ARCHIVE_FACE.width*1.04
          scaleY=detail.offsetHeight/viewport.height*visibleHeight/ARCHIVE_FACE.height*1.04
        } else finishPosition.set(narrow?0:.5,-.3,-12)
        finishPosition.applyQuaternion(camera.quaternion).add(camera.position)
        origin.copy(lockedOrigin);origin.z+=Math.sin(travel*Math.PI)*4
        extracted.position.lerpVectors(origin,finishPosition,travel)
        finishRotation.copy(camera.quaternion)
        extracted.quaternion.slerpQuaternions(lockedRotation,finishRotation,smooth((e-.18)/.62))
        extracted.scale.set(1+unfold*(scaleX-1),1+unfold*(scaleY-1),1-unfold*.5)
      }
      if(e===0){lockedOrigin=null;lockedRotation=null}
      lastExtraction=e
      ;(world.background as THREE.Color).copy(lightFog).lerp(darkFog,p)
      ;(world.fog as THREE.FogExp2).color.copy(lightFog).lerp(darkFog,p)
      bloom.strength=.06+p*.025+frame.energy*.08+Math.sin(e*Math.PI)*.08
      composer.render()
      host.dataset.selected=String(selected+1)
      host.dataset.extraction=e.toFixed(3)
      frames++
      host.dataset.frames=String(frames)
      host.dataset.yaw=helix.rotation.y.toFixed(5)
    },
    inspect() {
      world.updateMatrixWorld(true);camera.updateMatrixWorld(true)
      const origins=carriers.map(carrier=>carrier.getWorldPosition(new THREE.Vector3()).toArray())
      const ringBounds=Array.from({length:32},(_,i)=>rings.localToWorld(new THREE.Vector3(6.6*Math.cos(i*Math.PI/16),0,6.6*Math.sin(i*Math.PI/16))).project(camera).toArray())
      return {selected:selected+1,yaw:helix.rotation.y,pitch:helix.rotation.x,origins,projected:origins.map(v=>new THREE.Vector3().fromArray(v).project(camera).toArray()),ringBounds,extraction:lastExtraction,originError:lockedOrigin?lockedOrigin.distanceTo(carriers[selected].getWorldPosition(new THREE.Vector3())):null,visibleCarriers:carriers.filter(c=>c.visible).length,frames}
    },
    pick(x,y) {
      if(lastExtraction>.02)return null
      world.updateMatrixWorld(true);camera.updateMatrixWorld(true)
      raycaster.setFromCamera(new THREE.Vector2(x,y),camera)
      const hit=raycaster.intersectObjects(carriers,true).find(hit=>hit.object instanceof THREE.Mesh)
      if(!hit)return null
      selected=hit.object.userData.carrier as number
      return selected+1
    },
    dispose() {
      if(disposed)return;disposed=true;observer.disconnect()
      renderer.domElement.removeEventListener('webglcontextlost',lost)
      geometries.forEach(g=>g.dispose())
      strands.forEach(mesh=>(mesh.material as THREE.Material).dispose())
      selectionOutline.geometry.dispose();(selectionOutline.material as THREE.Material).dispose()
      ;[metal,porcelain,dark,yellow,glass,etched,strandMaterial,linksMaterial,ringMaterial,ringAccent].forEach(m=>m.dispose())
      bloom.dispose();output.dispose();composer.dispose();environment.dispose();renderer.dispose();renderer.forceContextLoss();renderer.domElement.remove()
    },
  }
}
