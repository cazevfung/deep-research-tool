"""Main Deep Research Agent orchestrator."""

from typing import Dict, Any, Optional
import os
from loguru import logger

from research.client import QwenStreamingClient
from research.session import ResearchSession
from research.progress_tracker import ProgressTracker
from research.phases.phase0_prepare import Phase0Prepare
from research.phases.phase0_5_role_generation import Phase0_5RoleGeneration
from research.phases.phase1_discover import Phase1Discover
from research.phases.phase2_finalize import Phase2Finalize
from research.phases.phase3_execute import Phase3Execute
from research.phases.phase4_synthesize import Phase4Synthesize
from research.ui.console_interface import ConsoleInterface
from pathlib import Path


class DeepResearchAgent:
    """Main orchestrator for deep research workflow."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
        model: Optional[str] = None,
        ui = None,
        additional_output_dirs: Optional[list] = None
    ):
        """
        Initialize research agent.
        
        Args:
            api_key: Qwen API key (defaults to env var or config.yaml)
            base_url: API base URL
            model: Model name (defaults to config.yaml qwen.model or "qwen3-max")
            ui: Optional UI interface (defaults to ConsoleInterface)
            additional_output_dirs: Optional list of additional directories to save reports to
        """
        self.client = QwenStreamingClient(api_key=api_key, base_url=base_url, model=model)
        self.ui = ui if ui is not None else ConsoleInterface()
        self.additional_output_dirs = additional_output_dirs or []
        
        logger.info("Initialized DeepResearchAgent")
    
    def _convert_questions_to_steps(
        self,
        phase1_goals: list,
        data_summary: Dict[str, Any]
    ) -> list:
        """
        Convert Phase 1 questions directly to research steps for Phase 3.
        
        Args:
            phase1_goals: List of goal objects from Phase 1
            data_summary: Summary of available data
            
        Returns:
            List of research plan steps
        """
        steps = []
        for i, goal in enumerate(phase1_goals, 1):
            goal_text = goal.get("goal_text", "")
            
            # Determine required_data based on goal uses
            uses = goal.get("uses", [])
            if isinstance(uses, list):
                if "transcript_with_comments" in uses or "comments" in uses:
                    required_data = "transcript_with_comments"
                elif "transcript" in uses:
                    required_data = "transcript"
                else:
                    required_data = "transcript_with_comments"  # Default
            else:
                required_data = "transcript_with_comments"  # Default
            
            # Determine chunk strategy based on data size
            total_words = data_summary.get("total_words", 0)
            if total_words > 50000:  # Large dataset
                chunk_strategy = "sequential"
            else:
                chunk_strategy = "all"
            
            step = {
                "step_id": i,
                "goal": goal_text,  # Use Phase 1 question directly
                "required_data": required_data,
                "chunk_strategy": chunk_strategy,
                "notes": f"直接回答研究问题：{goal_text}"
            }
            steps.append(step)
        
        return steps

    def run_phase0_prepare(
        self,
        *,
        batch_id: str,
        session: ResearchSession,
        force: bool = False,
    ) -> Dict[str, Any]:
        phase_key = "phase0"
        if not force:
            cached = session.get_phase_artifact(phase_key)
            if cached:
                return cached

        self.ui.display_header("Phase 0: 数据准备")
        phase0 = Phase0Prepare(self.client, session, ui=self.ui)
        phase0_result = phase0.execute(batch_id)

        abstracts = phase0_result.get("abstracts", {})
        combined_abstract = "\n\n---\n\n".join([
            f"**来源: {link_id}**\n{abstract}"
            for link_id, abstract in abstracts.items()
        ])

        MAX_ABSTRACT_LENGTH = 80000
        if len(combined_abstract) > MAX_ABSTRACT_LENGTH:
            logger.warning(
                f"Combined abstract too large ({len(combined_abstract)} chars), "
                f"truncating to {MAX_ABSTRACT_LENGTH} chars"
            )
            combined_abstract = combined_abstract[:MAX_ABSTRACT_LENGTH] + "\n\n[注意: 摘要已截断]"

        batch_data = phase0_result.get("data", {})
        try:
            session.batch_data = batch_data  # type: ignore[attr-defined]
        except Exception:
            session.set_metadata("_has_batch_data", True)

        sources = list(set([data.get("source", "unknown") for data in batch_data.values()]))
        total_words = sum([data.get("metadata", {}).get("word_count", 0) for data in batch_data.values()])
        total_comments = sum([
            len(data.get("comments") or [])
            for data in batch_data.values()
        ])

        quality_assessment = phase0_result.get("quality_assessment", {})

        if quality_assessment:
            quality_flags = quality_assessment.get("quality_flags", [])
            warnings = [f["message"] for f in quality_flags if f.get("severity") in ["warning", "error"]]
            if warnings:
                self.ui.display_message(
                    f"数据质量警告: {'; '.join(warnings[:2])}",
                    "warning"
                )

        transcript_sizes = []
        for data in batch_data.values():
            transcript = data.get("transcript", "")
            if transcript:
                word_count = len(transcript.split())
                transcript_sizes.append(word_count)

        transcript_size_analysis = {}
        if transcript_sizes:
            transcript_size_analysis = {
                "max_transcript_words": max(transcript_sizes),
                "avg_transcript_words": int(sum(transcript_sizes) / len(transcript_sizes)),
                "large_transcript_count": sum(1 for s in transcript_sizes if s > 5000),
                "total_transcripts": len(transcript_sizes)
            }

        data_summary = {
            "sources": sources,
            "total_words": total_words,
            "total_comments": total_comments,
            "num_items": len(batch_data),
            "quality_assessment": quality_assessment,
            "transcript_size_analysis": transcript_size_analysis
        }

        session.set_metadata("batch_id", batch_id)
        session.set_metadata("data_loaded", True)
        session.set_metadata("quality_assessment", quality_assessment)

        artifact = {
            "phase0_result": phase0_result,
            "combined_abstract": combined_abstract,
            "batch_data": batch_data,
            "data_summary": data_summary,
        }

        session.save_phase_artifact(phase_key, artifact)
        return artifact

    def run_phase0_5_role_generation(
        self,
        *,
        session: ResearchSession,
        combined_abstract: str,
        user_topic: Optional[str],
        force: bool = False,
    ) -> Dict[str, Any]:
        phase_key = "phase0_5"
        if not force:
            cached = session.get_phase_artifact(phase_key)
            if cached:
                return cached

        pre_role_feedback = session.get_metadata("phase_feedback_pre_role", "")
        if force or not pre_role_feedback:
            pre_role_feedback = self.ui.prompt_user(
                "在生成研究角色前，你想强调哪些研究重点或背景？(可选，留空表示无额外指导)"
            )
            session.set_metadata("phase_feedback_pre_role", pre_role_feedback or "")

        self.ui.display_header("Phase 0.5: 生成研究角色")
        phase0_5 = Phase0_5RoleGeneration(self.client, session, ui=self.ui)
        role_result = phase0_5.execute(
            combined_abstract,
            user_topic,
            user_guidance=pre_role_feedback or None,
        )
        research_role = role_result.get("research_role", None)
        if research_role:
            role_display = research_role.get("role", "") if isinstance(research_role, dict) else str(research_role)
            self.ui.display_message(f"生成的研究角色: {role_display}", "info")
        else:
            self.ui.display_message("未生成研究角色，将使用通用分析视角", "warning")

        artifact = {
            "role_result": role_result,
            "research_role": research_role,
            "pre_role_feedback": pre_role_feedback or "",
        }
        session.save_phase_artifact(phase_key, artifact)
        return artifact

    def run_phase1_discover(
        self,
        *,
        session: ResearchSession,
        combined_abstract: str,
        user_topic: Optional[str],
        research_role: Optional[Dict[str, Any]],
        pre_role_feedback: Optional[str],
        batch_data: Dict[str, Any],
        force: bool = False,
    ) -> Dict[str, Any]:
        phase_key = "phase1"
        if not force:
            cached = session.get_phase_artifact(phase_key)
            if cached:
                return cached

        self.ui.display_header("Phase 1: 生成研究目标")
        phase1 = Phase1Discover(self.client, session, ui=self.ui)
        phase1_result = phase1.execute(
            combined_abstract,
            user_topic,
            research_role=research_role,
            amendment_feedback=pre_role_feedback or None,
            batch_data=batch_data,
        )
        goals = phase1_result.get("suggested_goals", [])
        self.ui.display_goals(goals)

        post_phase1_feedback = self.ui.prompt_user("你想如何修改这些目标？(自由输入，留空表示批准并继续)")
        if post_phase1_feedback:
            amended_result = phase1.execute(
                combined_abstract,
                user_topic,
                research_role=research_role,
                amendment_feedback=post_phase1_feedback,
                batch_data=batch_data,
            )
            goals = amended_result.get("suggested_goals", [])
            self.ui.display_goals(goals)
            proceed = self.ui.prompt_user("是否采用这些修订后的目标并继续？(y/n)", ["y", "n"])
            if proceed == "y":
                phase1_result = amended_result
            else:
                logger.info("用户拒绝了修订后的目标，使用原始目标继续")
                goals = phase1_result.get("suggested_goals", [])

        session.set_metadata("phase1_confirmed_goals", goals)
        session.set_metadata("phase_feedback_post_phase1", post_phase1_feedback or "")
        session.set_metadata("phase1_user_input", post_phase1_feedback or "")
        session.save()

        artifact = {
            "phase1_result": phase1_result,
            "goals": goals,
            "post_phase1_feedback": post_phase1_feedback or "",
        }
        session.save_phase_artifact(phase_key, artifact)
        return artifact

    def run_phase2_synthesize(
        self,
        *,
        session: ResearchSession,
        phase1_artifact: Dict[str, Any],
        combined_abstract: str,
        user_topic: Optional[str],
        pre_role_feedback: Optional[str],
        force: bool = False,
    ) -> Dict[str, Any]:
        phase_key = "phase2"
        if not force:
            cached = session.get_phase_artifact(phase_key)
            if cached:
                return cached

        self.ui.display_header("Phase 2: 确定研究主题")
        phase2 = Phase2Finalize(self.client, session, ui=self.ui)
        phase1_result = phase1_artifact.get("phase1_result", {})
        post_phase1_feedback = phase1_artifact.get("post_phase1_feedback") or None
        phase2_result = phase2.execute(
            phase1_result,
            combined_abstract,
            user_input=post_phase1_feedback if post_phase1_feedback else None,
            user_topic=user_topic,
            pre_phase_feedback=pre_role_feedback or None,
        )

        synthesized = phase2_result.get("synthesized_goal", {})
        comprehensive_topic = synthesized.get("comprehensive_topic", "")
        component_questions = synthesized.get("component_questions", [])
        if not comprehensive_topic or not comprehensive_topic.strip():
            raise ValueError("Phase 2 failed to generate a comprehensive topic")

        self.ui.display_message("综合研究主题已生成", "success")
        self.ui.display_synthesized_goal(synthesized)

        phase1_goals = phase1_result.get("suggested_goals", [])
        data_summary = session.get_phase_artifact("phase0", {}).get("data_summary", {})
        plan = self._convert_questions_to_steps(phase1_goals, data_summary)

        logger.info(f"Converted {len(phase1_goals)} questions directly to {len(plan)} research steps")
        self.ui.display_plan(plan)
        session.set_metadata("research_plan", plan)

        artifact = {
            "phase2_result": phase2_result,
            "synthesized_goal": synthesized,
            "plan": plan,
        }
        session.save_phase_artifact(phase_key, artifact)
        return artifact

    def run_phase3_execute(
        self,
        *,
        session: ResearchSession,
        plan: list,
        batch_data: Dict[str, Any],
        force: bool = False,
        require_confirmation: bool = True,
    ) -> Dict[str, Any]:
        if not plan:
            raise ValueError("Phase 3 requires a non-empty research plan")

        phase_key = "phase3"
        if not force:
            cached = session.get_phase_artifact(phase_key)
            if cached and cached.get("plan_hash") == hash(str(plan)):
                return cached

        if require_confirmation:
            confirm = self.ui.prompt_user("是否继续执行计划? (y/n)", ["y", "n"])
            if confirm != "y":
                logger.info("User cancelled plan execution")
                return {"plan": plan, "phase3_result": None, "cancelled": True}

        progress_tracker = ProgressTracker(total_steps=len(plan))
        progress_tracker.add_callback(self.ui.display_progress)
        if hasattr(self.ui, 'display_step_complete'):
            progress_tracker.add_step_complete_callback(self.ui.display_step_complete)

        self.ui.display_header("Phase 3: 执行研究计划")
        phase3 = Phase3Execute(self.client, session, progress_tracker, ui=self.ui)
        phase3_result = phase3.execute(plan, batch_data)
        self.ui.display_message("研究计划执行完成", "success")

        session.set_metadata("report_stale", True)
        session.drop_phase_artifact("phase4", autosave=False)

        artifact = {
            "phase3_result": phase3_result,
            "plan": plan,
            "plan_hash": hash(str(plan)),
        }
        session.save_phase_artifact(phase_key, artifact)
        return artifact

    def rerun_phase3_step(
        self,
        *,
        session: ResearchSession,
        plan: list,
        batch_data: Dict[str, Any],
        step_id: int,
    ) -> Dict[str, Any]:
        if not plan:
            raise ValueError("Cannot rerun Phase 3 step without an existing plan")

        step_lookup = {step.get("step_id"): step for step in plan if step}
        target_step = step_lookup.get(step_id)
        if not target_step:
            raise ValueError(f"Step {step_id} not found in research plan")

        self.ui.display_header(f"Phase 3: 重新执行步骤 {step_id}")

        progress_tracker = ProgressTracker(total_steps=1)
        progress_tracker.add_callback(self.ui.display_progress)
        if hasattr(self.ui, 'display_step_complete'):
            progress_tracker.add_step_complete_callback(self.ui.display_step_complete)

        phase3 = Phase3Execute(self.client, session, progress_tracker, ui=self.ui)
        step_result = phase3.execute([target_step], batch_data)
        self.ui.display_message(f"步骤 {step_id} 已重新执行", "success")

        new_finding_entries = step_result.get("findings", [])
        new_finding = None
        if isinstance(new_finding_entries, list) and new_finding_entries:
            new_finding = new_finding_entries[0]

        existing_artifact = session.get_phase_artifact("phase3") or {}
        existing_result = existing_artifact.get("phase3_result", {})
        findings_list = existing_result.get("findings", [])

        replaced = False
        for idx, entry in enumerate(findings_list):
            if entry.get("step_id") == step_id and new_finding:
                findings_list[idx] = new_finding
                replaced = True
                break

        if not replaced and new_finding:
            findings_list.append(new_finding)

        unique_steps = {entry.get("step_id") for entry in findings_list if isinstance(entry, dict)}
        existing_result["findings"] = findings_list
        existing_result["completed_steps"] = len(unique_steps)
        existing_result["telemetry"] = step_result.get("telemetry", {})

        # Preserve plan reference and hash
        artifact = {
            "phase3_result": existing_result,
            "plan": plan,
            "plan_hash": hash(str(plan)),
        }

        session.set_metadata("report_stale", True)
        session.drop_phase_artifact("phase4", autosave=False)
        session.save_phase_artifact("phase3", artifact)
        session.save()

        return artifact

    def run_phase4_synthesize(
        self,
        *,
        session: ResearchSession,
        phase2_artifact: Dict[str, Any],
        phase3_artifact: Dict[str, Any],
        batch_id: str,
        force: bool = False,
    ) -> Dict[str, Any]:
        phase_key = "phase4"
        if not force:
            cached = session.get_phase_artifact(phase_key)
            if cached:
                return cached

        self.ui.display_header("Phase 4: 生成最终报告")
        phase4 = Phase4Synthesize(self.client, session, progress_tracker=None, ui=self.ui)
        self.ui.clear_stream_buffer()

        phase4_result = phase4.execute(
            phase1_5_output=phase2_artifact.get("phase2_result"),
            phase3_output=phase3_artifact.get("phase3_result"),
        )

        report = phase4_result.get("report", "")
        from datetime import datetime

        reports_dir = Path(__file__).parent.parent / "tests" / "results" / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        report_file = reports_dir / f"report_{batch_id}_{session.session_id}.md"
        synthesized_goal = phase2_artifact.get("synthesized_goal", {})
        comprehensive_topic = synthesized_goal.get("comprehensive_topic", "")

        report_content = (
            f"# 研究报告\n\n"
            f"**研究目标**: {comprehensive_topic}\n\n"
            f"**生成时间**: {datetime.now().isoformat()}\n\n"
            f"**批次ID**: {batch_id}\n\n"
            f"---\n\n"
            f"{report}"
        )

        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report_content)

        additional_paths = []
        for output_dir in self.additional_output_dirs:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            additional_file = output_path / f"report_{batch_id}_{session.session_id}.md"
            with open(additional_file, 'w', encoding='utf-8') as f:
                f.write(report_content)
            additional_paths.append(str(additional_file))
            logger.info(f"Report also saved to: {additional_file}")

        self.ui.display_report(report, str(report_file))

        artifact = {
            "phase4_result": phase4_result,
            "report_path": str(report_file),
            "report_content": report_content,
            "additional_report_paths": additional_paths,
        }
        session.set_metadata("report_stale", False)
        session.save_phase_artifact(phase_key, artifact)
        return artifact
    
    def run_research(
        self,
        batch_id: str,
        user_topic: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        if session_id:
            try:
                session = ResearchSession.load(session_id)
                logger.info(f"Resumed session: {session_id}")
            except FileNotFoundError:
                logger.warning(f"Session not found: {session_id}, creating new")
                session = ResearchSession(session_id=session_id)
        else:
            session = ResearchSession()

        logger.info(f"Starting research for batch: {batch_id}, session: {session.session_id}")
        session.set_metadata("user_topic", user_topic or "")

        try:
            phase0_artifact = self.run_phase0_prepare(
                batch_id=batch_id,
                session=session,
                force=True,
            )
            phase0_5_artifact = self.run_phase0_5_role_generation(
                session=session,
                combined_abstract=phase0_artifact["combined_abstract"],
                user_topic=user_topic,
                force=True,
            )
            phase1_artifact = self.run_phase1_discover(
                session=session,
                combined_abstract=phase0_artifact["combined_abstract"],
                user_topic=user_topic,
                research_role=phase0_5_artifact.get("research_role"),
                pre_role_feedback=phase0_5_artifact.get("pre_role_feedback"),
                batch_data=phase0_artifact["batch_data"],
                force=True,
            )
            phase2_artifact = self.run_phase2_synthesize(
                session=session,
                phase1_artifact=phase1_artifact,
                combined_abstract=phase0_artifact["combined_abstract"],
                user_topic=user_topic,
                pre_role_feedback=phase0_5_artifact.get("pre_role_feedback"),
                force=True,
            )

            plan = phase2_artifact.get("plan", [])
            if not plan:
                raise ValueError("Phase 2 did not produce a valid research plan")

            phase3_artifact = self.run_phase3_execute(
                session=session,
                plan=plan,
                batch_data=phase0_artifact["batch_data"],
                force=True,
            )
            if phase3_artifact.get("cancelled"):
                return {"status": "cancelled"}

            phase4_artifact = self.run_phase4_synthesize(
                session=session,
                phase2_artifact=phase2_artifact,
                phase3_artifact=phase3_artifact,
                batch_id=batch_id,
                force=True,
            )

            synthesized_goal = phase2_artifact.get("synthesized_goal", {})
            comprehensive_topic = synthesized_goal.get("comprehensive_topic", "")

            session.set_metadata("status", "completed")
            from datetime import datetime
            session.set_metadata("completed_at", datetime.now().isoformat())
            session.set_metadata("finished", True)
            session.set_metadata("selected_goal", comprehensive_topic)
            session.save()

            logger.info("")
            logger.success("=" * 60)
            logger.success("  RESEARCH SESSION FINISHED - SUCCESSFULLY COMPLETED")
            logger.success("=" * 60)
            logger.success(f"  Session ID: {session.session_id}")
            logger.success(f"  Batch ID: {batch_id}")
            logger.success(f"  Report saved to: {phase4_artifact.get('report_path')}")
            additional_paths = phase4_artifact.get("additional_report_paths") or []
            if additional_paths:
                logger.success(f"  Additional report: {additional_paths[0]}")
            usage_info = self.client.get_usage_info()
            logger.success(f"  Total tokens used: {usage_info.get('total_tokens', 0)}")
            logger.success("=" * 60)
            logger.success("  RESEARCH COMPLETE - NO FURTHER ACTION REQUIRED")
            logger.success("=" * 60)
            logger.info("")

            return {
                "status": "completed",
                "session_id": session.session_id,
                "batch_id": batch_id,
                "report_path": phase4_artifact.get("report_path"),
                "additional_report_paths": additional_paths,
                "selected_goal": comprehensive_topic,
                "usage": usage_info
            }

        except Exception as e:
            logger.error(f"Research failed: {str(e)}")
            self.ui.display_message(f"错误: {str(e)}", "error")
            raise

