from typing import Any, Dict, List, NamedTuple
from functools import cached_property

from pydantic import BaseModel

from .field_types import BaseField
from .FieldResolver import FieldResolver
from .rules import MatchedRule, RuleRegistry, RuleParser


class ContractWithoutFields(Exception):
    pass


class ContractWithoutName(Exception):
    pass


class Field(NamedTuple):
    field_name: str
    field_type: str
    field_rules: List[str]


class Contract:
    name: str
    fields: List[Field]
    rule_parser: RuleParser
    field_resolvers: Dict[str, FieldResolver]


    def __init__(self, name: str, fields: List[Field], values: Dict[str, Any]) -> None:
        self.name = name
        self.fields = fields
        self.rule_parser = RuleParser(values)
        self.field_resolvers = {
            field_type: FieldResolver(RuleRegistry.get_type(field_type), self.rule_parser)
            for field_type in list({field.field_type for field in self.fields})  # Unique types
        }

    @classmethod
    def from_dict(cls, contract_dict: dict):
        if "name" not in contract_dict:
            raise ContractWithoutName()
        if "fields" not in contract_dict:
            raise ContractWithoutFields()

        return cls(
            name=contract_dict["name"],
            fields=[Field(**field) for field in contract_dict["fields"]],
            values=contract_dict.get("values", {}),
        )

    @cached_property
    def field_validators(self) -> Dict[str, BaseField]:
        field_validators = {}
        for field in self.fields:
            field_resolver = self.field_resolvers[field.field_type]
            field_validators[field.field_name] = field_resolver.get_field_validator(field.field_name, field.field_rules)
        return field_validators

    @cached_property
    def rules(self) -> Dict[str, List[MatchedRule]]:
        rules = {}
        for field in self.fields:
            field_resolver = self.field_resolvers[field.field_type]
            rules[field.field_name] = field_resolver.get_matched_rules(field.field_rules)
        return rules

    def model_validate(self, item: dict):
        pydantic_model = self.get_pydantic_model()
        return pydantic_model.model_validate(item).model_dump()

    def get_pydantic_model(self) -> BaseModel:
        return type(self.name, (BaseModel,), {
            "__annotations__": {
                field_name: field_validator.get_annotation()
                for field_name, field_validator in self.field_validators.items()
            }
        })

    def get_front_end_contract(self):
        return {
            "name": self.name,
            "fields": [
                {
                    "field_name": field_name,
                    "field_type": field_validator.__class__.__name__,
                    "field_rules": [
                        {
                            "rule": rule.field_rule,
                            "parsed_rule": rule.parsed_rule,
                            "rule_params": rule.rule_params,
                            "parsed_values": rule.parsed_values,
                        }
                        for rule in self.rules.get(field_name, [])
                    ]
                }
                for field_name, field_validator in self.field_validators.items()
            ],
            "values": self.rule_parser.values
        }
