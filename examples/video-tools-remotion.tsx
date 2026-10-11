import React from 'react';
import {AbsoluteFill, Composition, Img, interpolate, registerRoot, staticFile, useCurrentFrame} from 'remotion';
const Video = (props:any) => {
  const f=useCurrentFrame();
  const scale=(props.width||1280)/1280;
  const opacity=interpolate(f,[0,18],[0,1],{extrapolateRight:'clamp'});
  const rise=interpolate(f,[0,24],[36,0],{extrapolateRight:'clamp'});
  return <AbsoluteFill style={{background:props.background||'#111c30',color:'#f1f6ff',fontFamily:'sans-serif',padding:64*scale,justifyContent:'center'}}>
    {props.image&&<Img src={staticFile(props.image)} style={{position:'absolute',inset:0,width:'100%',height:'100%',objectFit:'cover',opacity:.3}}/>}
    <div style={{opacity,transform:`translateY(${rise}px)`,position:'relative'}}>
      <div style={{fontSize:24*scale,color:'#82b3ff',marginBottom:24*scale}}>{props.eyebrow||'AI VIDEO STUDIO'}</div>
      <div style={{fontSize:64*scale,fontWeight:700,lineHeight:1.2}}>{props.title||'把想法制作成视频'}</div>
      <div style={{fontSize:28*scale,marginTop:24*scale,lineHeight:1.6,color:'#bccce3'}}>{props.subtitle||'素材 · 分镜 · 动效 · 配音 · 交付'}</div>
      <div style={{height:6*scale,marginTop:48*scale,width:`${interpolate(f,[0,120],[0,100],{extrapolateRight:'clamp'})}%`,background:'#82b3ff'}}/>
    </div>
  </AbsoluteFill>;
};
registerRoot(()=> <Composition id="Video" component={Video} width={1280} height={720} fps={24} durationInFrames={144}
 defaultProps={{title:'',subtitle:''}} calculateMetadata={({props}:any)=>({width:props.width||1280,height:props.height||720,fps:props.fps||24,durationInFrames:Math.round((props.duration||6)*(props.fps||24))})}/>);
