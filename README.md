# Prompt Compare

A streamlined toolkit for A/B testing and comparing AI prompt performance with side-by-side analysis, HTML dashboards, and Excel reporting.

## Overview

This tool enables rapid comparison of different prompt versions by:
- Running automated A/B tests against API endpoints
- Validating links in responses 
- Generating interactive HTML dashboards
- Creating clean Excel reports for analysis

## Features

✨ **Side-by-side prompt comparison** - Test 2 prompt versions simultaneously  
📊 **Interactive HTML dashboard** - Expandable question-by-question comparison  
📈 **Clean Excel reports** - Professional formatting with uniform rectangular layout  
🔗 **Link validation** - Automatic validation of URLs in responses  
⚡ **Fast workflow** - No LLM judging required, immediate results  

## Quick Start

### 1. Run Prompt Comparison Test

```bash
python3 src/multi_prompt_evaluator.py \
  --endpoint https://your-api-endpoint.com/sync_query \
  --auth "" \
  --questions examples_questions.json \
  --name "Your A vs B Test" \
  --description "Comparison of prompt versions A and B" \
  --prompt1-name "Prompt Version A" \
  --prompt1-desc "Current baseline prompt" \
  --prompt2-name "Prompt Version B" \
  --prompt2-desc "Modified test prompt" \
  --delay-questions 2.0 \
  --delay-prompts 5.0
```

### 2. Generate HTML Dashboard

```bash
python3 question_comparison_dashboard.py \
  --input your_evaluation_results.json \
  --output comparison_dashboard.html
```

### 3. Create Excel Report

```bash
python3 convert_multi_prompt_to_excel.py \
  --input your_evaluation_results.json \
  --output prompt_comparison.xlsx
```

## File Structure

```
prompt-compare/
├── src/
│   ├── multi_prompt_evaluator.py      # Main evaluation engine
│   ├── api_test_harness.py           # API testing infrastructure  
│   └── enhanced_link_validation.py    # Link validation logic
├── question_comparison_dashboard.py   # HTML dashboard generator
├── convert_multi_prompt_to_excel.py  # Excel report generator
├── examples_questions.json           # Sample questions file
└── README.md                         # This file
```

## Question File Format

Questions should be in JSON format:

```json
[
  {
    "id": "Q001",
    "question": "Your question text here?",
    "category": "general",
    "complexity": "basic"
  }
]
```

## API Endpoint Requirements

Your API endpoint should:
- Accept POST requests with JSON payload
- Use format: `{"followUpText":"[{\"question\":\"...\",\"response\":\"\"}]","conversationId":"TEST"}`
- Return JSON with `"response"` field containing the answer

## Workflow

1. **Setup Questions**: Create JSON file with your test questions
2. **Run Evaluation**: Use `multi_prompt_evaluator.py` to test both prompts
3. **Manual Prompt Switching**: Script pauses between prompts for you to update your system prompt
4. **Generate Outputs**: Create HTML dashboard and/or Excel report
5. **Analyze Results**: Compare responses side-by-side

## Output Files

### HTML Dashboard
- Interactive question list (click to expand)
- Side-by-side response comparison
- Response time and link validation metrics
- Mobile-responsive design

### Excel Report
- Clean rectangular layout
- 5 columns: Question | Answer A | Answer B | Links A | Links B
- Color-coded for easy comparison
- Professional formatting with borders and consistent sizing

## Dependencies

```bash
pip install requests pandas openpyxl
```

## Example Use Cases

- **Prompt Engineering**: Test different system prompts
- **A/B Testing**: Compare response quality between prompt versions  
- **Performance Analysis**: Measure response times and link validation
- **Documentation**: Generate reports for stakeholders
- **Quality Assurance**: Validate chatbot responses across question sets

## Indiana OALP Example

This toolkit was originally developed for testing the Indiana Office of Administrative Law Proceedings (OALP) chatbot. The `examples_questions.json` contains legal questions used in that evaluation.

## Contributing

Feel free to submit issues and enhancement requests!

## License

MIT License - Feel free to use and modify as needed.